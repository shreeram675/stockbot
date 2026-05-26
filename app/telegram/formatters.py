from app.schemas.portfolio import PortfolioView


def money(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    return f"Rs. {value:,.2f}"


def pct(value: float | None) -> str:
    if value is None:
        return "Unavailable"
    return f"{value:+.2f}%"


def format_statuses(statuses) -> str:
    failed = [s for s in statuses if not s.ok]
    if not failed:
        return ""
    lines = ["", "⚠️ Data Notes"]
    lines.extend(f"- {s.service}: {s.message}" for s in failed[:5])
    return "\n".join(lines)


def format_portfolio(portfolio: PortfolioView, ai_commentary: str | None = None) -> str:
    top = sorted(portfolio.holdings, key=lambda h: h.market_value, reverse=True)[:5]
    lines = [
        "📊 Portfolio Snapshot",
        "━━━━━━━━━━━━━━━━━━━━",
        f"💼 Value: {money(portfolio.portfolio_value)}",
        f"🏦 Invested: {money(portfolio.invested_amount)}",
        f"📈 P&L: {money(portfolio.pnl)}",
        f"🌤 Daily P&L: {money(portfolio.daily_pnl)}",
        "",
        "🏁 Top Holdings",
    ]
    if top:
        lines.extend(
            f"- {h.symbol}: {money(h.market_value)} ({portfolio.allocation.get(h.symbol, 0):.2f}%)"
            for h in top
        )
    else:
        lines.append("- No holdings returned by Dhan.")
    if ai_commentary:
        lines.extend(["", "🧠 AI Commentary", ai_commentary])
    lines.append(format_statuses(portfolio.statuses))
    return "\n".join(line for line in lines if line is not None)


def format_holdings(portfolio: PortfolioView) -> str:
    lines = ["📦 Holdings", "━━━━━━━━━━━━━━━━━━━━"]
    if not portfolio.holdings:
        lines.append("No holdings returned by Dhan.")
    for h in portfolio.holdings[:25]:
        lines.extend(
            [
                f"🔹 {h.symbol}",
                f"   Qty: {h.quantity:g} | Avg: {money(h.average_price)}",
                f"   Value: {money(h.market_value)} | P&L: {money(h.gain_loss)}",
            ]
        )
    lines.append(format_statuses(portfolio.statuses))
    return "\n".join(lines)


def format_performance(perf: dict) -> str:
    lines = [
        "📈 Performance",
        "━━━━━━━━━━━━━━━━━━━━",
        f"Daily return: {pct(perf.get('daily_return'))}",
        f"Weekly return: {pct(perf.get('weekly_return'))}",
        f"Monthly return: {pct(perf.get('monthly_return'))}",
        f"Top performer: {perf.get('top_performer') or 'Unavailable'}",
        f"Worst performer: {perf.get('worst_performer') or 'Unavailable'}",
        f"Trend: {perf.get('trend')}",
    ]
    return "\n".join(lines)


def format_health(health: dict) -> str:
    lines = ["🩺 Portfolio Health", "━━━━━━━━━━━━━━━━━━━━", f"Score: {health['score']}/100", ""]
    for name, item in health["components"].items():
        lines.append(f"• {name.replace('_', ' ').title()}: {item['score']}/25")
        lines.append(f"  {item['reason']}")
    return "\n".join(lines)


def format_market_report(title: str, overview: dict, news: list[dict], warnings: list[str], insight: str | None) -> str:
    lines = [title, "━━━━━━━━━━━━━━━━━━━━", "🌍 Market Overview"]
    for label, quote in overview.items():
        lines.append(f"- {label}: {money(quote.get('price'))} ({pct(quote.get('change_percent'))})")
    lines.append("")
    lines.append("📰 Finnhub Headlines")
    if news:
        lines.extend(f"- {item.get('headline', 'Untitled')}" for item in news[:5])
    else:
        lines.append("Finnhub news unavailable.")
    if insight:
        lines.extend(["", "🧠 AI Insight", insight])
    if warnings:
        lines.extend(["", "⚠️ Data Notes", *[f"- {w}" for w in warnings[:5]]])
    return "\n".join(lines)


def format_weekly_report(data: dict) -> str:
    return "\n".join(
        [
            "📅 Weekly Report",
            "━━━━━━━━━━━━━━━━━━━━",
            f"Portfolio value: {money(data['value'])}",
            f"Weekly growth: {pct(data['weekly_growth'])}",
            "",
            "Allocation",
            *[f"- {k}: {v:.2f}%" for k, v in data["allocation"].items()],
        ]
    )


def format_monthly_workflow(risk_profile: str, budget: int, recommendation: str) -> str:
    return "\n".join(
        [
            "🗓 Monthly Investment Workflow",
            "━━━━━━━━━━━━━━━━━━━━",
            f"Risk profile: {risk_profile}",
            f"Budget: Rs. {budget:,}",
            "",
            "🧠 Rebalance Plan",
            recommendation,
        ]
    )
