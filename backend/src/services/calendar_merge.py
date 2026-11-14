"""领用日历接续合并的纯函数核心。

ERP 补发/更正日历时在既有批次上接续：按备件+日期合并，重复投递幂等跳过，
同日不同数量列为冲突待人工取舍，日历断档物化为缺报标记（与明确零领用分开）。
本模块不依赖 Web 框架，便于独立测试；异常用 ValueError 表达，由服务层映射为 HTTP 错误。
"""
from datetime import date, timedelta
import math

MAX_ROWS = 5000
MISSING_LABEL = '日历断档 · 待补发'


class UnchangedMerge(ValueError):
    """补发内容与现有日历完全一致，无需生成新批次。"""


def _day(value, index):
    try:
        return str(date.fromisoformat(str(value).strip()))
    except (TypeError, ValueError):
        raise ValueError(f'第 {index} 行领用日必须是 ISO 日期（例如 2026-07-14）') from None


def _demand(value, index):
    """返回 None 表示缺报标记；否则为有限数值。"""
    if value is None or (isinstance(value, str) and not value.strip()):
        return None
    if isinstance(value, bool):
        raise ValueError(f'第 {index} 行领用件数必须为有限数值，留空表示缺报')
    try:
        amount = float(value)
    except (TypeError, ValueError, OverflowError):
        raise ValueError(f'第 {index} 行领用件数必须为有限数值，留空表示缺报') from None
    if not math.isfinite(amount):
        raise ValueError(f'第 {index} 行领用件数必须为有限数值，留空表示缺报')
    return amount


def _rows(records):
    for index, row in enumerate(records, 1):
        part = str(row.get('part') or '').strip()
        if not part:
            raise ValueError(f'第 {index} 行缺少备件编码')
        yield part, _day(row.get('day'), index), _demand(row.get('demand'), index)


def plan_merge(base_records, base_sources, base_label, incoming, upload_label):
    """生成合并计划，不修改任何数据。

    base_sources: 原批次逐条来源映射（'备件|日期' -> 来源说明），无则统一使用 base_label。
    返回 merged 全量索引与 added/duplicates/fills/conflicts 统计。
    """
    merged = {}
    for part, day, demand in _rows(base_records):
        key = (part, day)
        if key in merged:
            raise ValueError(f'原批次存在重复日历记录：{part} {day}')
        merged[key] = {'part': part, 'day': day, 'demand': demand,
                       'source': base_sources.get(f'{part}|{day}', base_label)}
    added = duplicates = fills = 0
    conflicts = {}
    for part, day, demand in _rows(incoming):
        key = (part, day)
        current = merged.get(key)
        if current is None:
            merged[key] = {'part': part, 'day': day, 'demand': demand, 'source': upload_label}
            added += 1
        elif demand is None:
            duplicates += 1  # 缺报标记不覆盖已有记录
        elif current['demand'] is None:
            current['demand'] = demand
            current['source'] = upload_label
            fills += 1  # 补发正好补齐缺报日
        elif current['demand'] == demand:
            duplicates += 1  # 重复投递，幂等跳过，不重复计算领用量
        else:
            conflict = conflicts.setdefault(key, {'part': part, 'day': day, 'existing': current['demand'],
                                                  'existing_source': current['source'], 'candidates': []})
            if demand not in conflict['candidates']:
                conflict['candidates'].append(demand)
    return {'merged': merged, 'added': added, 'duplicates': duplicates, 'fills': fills,
            'conflicts': list(conflicts.values())}


def find_holes(merged):
    """每个备件日历范围内既无领用记录也无缺报标记的断档日期。"""
    by_part = {}
    for item in merged.values():
        by_part.setdefault(item['part'], set()).add(item['day'])
    holes = []
    for part, days in by_part.items():
        current = date.fromisoformat(min(days))
        end = date.fromisoformat(max(days))
        while current <= end:
            if str(current) not in days:
                holes.append({'part': part, 'day': str(current)})
            current += timedelta(days=1)
    return sorted(holes, key=lambda h: (h['part'], h['day']))


def preview(plan):
    """预检结果：统计、冲突清单、断档缺报清单，供人工确认后再提交。"""
    holes = find_holes(plan['merged'])
    missing = sum(1 for item in plan['merged'].values() if item['demand'] is None) + len(holes)
    return {'added': plan['added'], 'duplicates': plan['duplicates'], 'fills': plan['fills'],
            'conflicts': plan['conflicts'], 'holes': holes, 'missing_total': missing,
            'rows_after': len(plan['merged']) + len(holes),
            'over_limit': len(plan['merged']) + len(holes) > MAX_ROWS,
            'unchanged': not (plan['added'] or plan['fills'] or holes or plan['conflicts'])}


def finalize_merge(plan, resolutions, upload_label, decider, at, max_rows=MAX_ROWS):
    """按确认的取舍生成新批次记录与溯源。resolutions: {(part, day): demand}。"""
    merged = plan['merged']
    known = {(c['part'], c['day']): c for c in plan['conflicts']}
    unknown = [key for key in resolutions if key not in known]
    if unknown:
        part, day = sorted(unknown)[0]
        raise ValueError(f'取舍决定包含非冲突记录：{part} {day}')
    pending = [key for key in known if key not in resolutions]
    if pending:
        raise ValueError(f'还有 {len(pending)} 条同日不同数量冲突未确认取舍')
    decisions = []
    for key, conflict in known.items():
        chosen = resolutions[key]
        options = [conflict['existing']] + conflict['candidates']
        if chosen not in options:
            raise ValueError(f"{conflict['part']} {conflict['day']} 的取舍值必须等于原值 {conflict['existing']:g} 或补发值之一")
        source = conflict['existing_source'] if chosen == conflict['existing'] else upload_label
        merged[key] = {'part': conflict['part'], 'day': conflict['day'], 'demand': chosen, 'source': source}
        decisions.append({'part': conflict['part'], 'day': conflict['day'], 'existing': conflict['existing'],
                          'candidates': conflict['candidates'], 'adopted': chosen, 'source': source,
                          'by': decider, 'at': at})
    holes = find_holes(merged)
    for hole in holes:
        merged[(hole['part'], hole['day'])] = {'part': hole['part'], 'day': hole['day'],
                                               'demand': None, 'source': MISSING_LABEL}
    if not (plan['added'] or plan['fills'] or holes or decisions):
        raise UnchangedMerge('补发内容与现有日历完全一致，无需生成新批次')
    items = sorted(merged.values(), key=lambda i: (i['part'], i['day']))
    if len(items) > max_rows:
        raise ValueError(f'合并后共 {len(items)} 条，超过单批次 {max_rows} 条上限，请分批接续')
    records = [{'day': item['day'], 'part': item['part'], 'demand': item['demand']} for item in items]
    stats = {'added': plan['added'], 'duplicates': plan['duplicates'], 'fills': plan['fills'],
             'conflicts': len(decisions), 'holes': len(holes),
             'missing_total': sum(1 for item in items if item['demand'] is None),
             'rows': len(items)}
    provenance = {'record_sources': {f"{item['part']}|{item['day']}": item['source'] for item in items},
                  'decisions': decisions, 'stats': stats}
    return records, provenance, stats
