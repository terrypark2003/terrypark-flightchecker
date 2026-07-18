"""가격 이력 그래프 렌더링 (matplotlib → PNG bytes).

서버(Railway) 컨테이너에 한글 폰트가 없어도 깨지지 않도록
그래프 안의 글자는 공항 코드·숫자 등 ASCII만 사용합니다.
"""

from __future__ import annotations

import io
from datetime import datetime


def render_price_chart(
    points: list[tuple[datetime, float]],
    title: str,
    target_price: float | None = None,
    currency: str = "KRW",
) -> bytes:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.dates import DateFormatter
    from matplotlib.ticker import FuncFormatter

    xs = [t for t, _ in points]
    ys = [p for _, p in points]

    fig, ax = plt.subplots(figsize=(8, 4.5), dpi=110)
    ax.plot(xs, ys, marker="o", linewidth=1.8, color="tab:blue")

    if target_price:
        ax.axhline(
            target_price, linestyle="--", color="tab:red", alpha=0.7,
            label=f"target {target_price:,.0f}",
        )
        ax.legend(loc="best")

    # 최저점 강조
    low_i = min(range(len(ys)), key=lambda i: ys[i])
    ax.annotate(
        f"{ys[low_i]:,.0f}",
        (xs[low_i], ys[low_i]),
        textcoords="offset points", xytext=(0, -14),
        ha="center", fontsize=9, color="tab:green",
    )

    ax.set_title(title)
    ax.set_ylabel(currency)
    ax.grid(alpha=0.3)
    ax.xaxis.set_major_formatter(DateFormatter("%m/%d %H:%M"))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}"))
    fig.autofmt_xdate()
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    plt.close(fig)
    return buf.getvalue()
