"""与 Cloud 保持一致的打印纸张和额度计算。"""


def quota_usage(
    page_count: int,
    copies: int,
    duplex_mode: str,
    color_mode: str,
    impressions_completed: int | None = None,
) -> dict[str, int]:
    if page_count < 1 or copies < 1:
        raise ValueError("page_count and copies must be positive")
    if duplex_mode not in {"simplex", "longedge", "shortedge"}:
        raise ValueError("unsupported duplex mode")
    if color_mode not in {"mono", "color"}:
        raise ValueError("unsupported color mode")

    maximum_impressions = page_count * copies
    impressions = maximum_impressions if impressions_completed is None else impressions_completed
    if impressions < 0 or impressions > maximum_impressions:
        raise ValueError("impressions_completed is outside the authorized range")

    if duplex_mode == "simplex":
        sheets = impressions
    else:
        complete_copies, remaining_impressions = divmod(impressions, page_count)
        sheets = complete_copies * ((page_count + 1) // 2)
        sheets += (remaining_impressions + 1) // 2

    multiplier = 2 if color_mode == "color" else 1
    return {
        "impressions": impressions,
        "sheets": sheets,
        "points": sheets * multiplier,
    }
