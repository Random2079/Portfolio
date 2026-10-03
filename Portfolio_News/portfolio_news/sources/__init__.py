from portfolio_news.sources.google_news_ru import GoogleNewsRuSource
from portfolio_news.sources.pulse_allowlist import PulseAllowlistSource
from portfolio_news.sources.pulse_news_ticker import PulseNewsTickerSource
from portfolio_news.sources.smartlab import SmartLabRssSource
from portfolio_news.sources.telegram_allowlist import TelegramAllowlistSource


def default_sources():
    return [
        GoogleNewsRuSource(),
        SmartLabRssSource(),
        PulseAllowlistSource(),
        PulseNewsTickerSource(),
        TelegramAllowlistSource(),
    ]
