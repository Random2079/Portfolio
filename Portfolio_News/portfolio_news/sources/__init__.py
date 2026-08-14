from portfolio_news.sources.google_news_ru import GoogleNewsRuSource
from portfolio_news.sources.smartlab import SmartLabRssSource


def default_sources():
    return [GoogleNewsRuSource(), SmartLabRssSource()]
