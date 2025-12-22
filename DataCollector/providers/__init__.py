# DataCollector/providers/__init__.py
"""
Data provider modules for fetching market data from various sources.
Exports provider classes and factory function.
"""

from DataCollector.providers.base_provider import (
    BaseDataProvider,
    ProviderError,
    RateLimitError,
    DataNotFoundError,
    AuthenticationError,
)
from DataCollector.providers.yahoo_provider import YahooFinanceProvider
from DataCollector.providers.nse_provider import NSEProvider
from DataCollector.providers.bse_provider import BSEProvider
from DataCollector.providers.zerodha_provider import ZerodhaProvider


def get_provider(provider_name: str, **kwargs) -> BaseDataProvider:
    """
    Factory function to get a data provider instance by name.
    
    Args:
        provider_name: Name of the provider (yahoo, nse, bse, zerodha)
        **kwargs: Provider-specific configuration
    
    Returns:
        BaseDataProvider: Provider instance
    
    Raises:
        ValueError: If provider name is not recognized
    
    Example:
        >>> provider = get_provider("yahoo")
        >>> data = provider.get_historical_data("RELIANCE.NS", "2024-01-01", "2024-12-20")
    """
    providers = {
        "yahoo": YahooFinanceProvider,
        "nse": NSEProvider,
        "bse": BSEProvider,
        "zerodha": ZerodhaProvider,
    }
    
    if provider_name.lower() not in providers:
        raise ValueError(
            f"Unknown provider: {provider_name}. "
            f"Available providers: {list(providers.keys())}"
        )
    
    return providers[provider_name.lower()](**kwargs)


__all__ = [
    # Base classes and exceptions
    "BaseDataProvider",
    "ProviderError",
    "RateLimitError",
    "DataNotFoundError",
    "AuthenticationError",
    # Providers
    "YahooFinanceProvider",
    "NSEProvider",
    "BSEProvider",
    "ZerodhaProvider",
    # Factory
    "get_provider",
]
