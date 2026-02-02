"""Strategy registry for mapping strategy keys to engine implementations.

This module provides a centralized registry to map user-facing strategy keys
(e.g., 'hidden_dragon', 'turtle') to their internal engine class paths.

This avoids exposing implementation details in the database.
"""

from typing import Dict, Optional


class StrategyRegistry:
    """Registry for vnpy strategy implementations."""
    
    # Strategy key -> Engine class path mapping
    _VNPY_STRATEGIES: Dict[str, str] = {
        "hidden_dragon": "scripts.single_stream_hidden_dragon.SingleStreamRealTimeEngine",
        "turtle": "scripts.single_stream_turtle.SingleStreamRealTimeEngine",
        "single_yang": "scripts.single_stream_single_yang.SingleStreamRealTimeEngine",
        "grid": "scripts.single_stream_grid.SingleStreamRealTimeEngine",
        # Add more strategies here as they are developed
    }
    
    @classmethod
    def get_vnpy_engine_class(cls, strategy_key: str) -> Optional[str]:
        """
        Get vnpy engine class path for a strategy key.
        
        Args:
            strategy_key: User-facing strategy identifier (e.g., 'hidden_dragon')
            
        Returns:
            Full class path or None if not found
            
        Example:
            >>> StrategyRegistry.get_vnpy_engine_class('hidden_dragon')
            'scripts.single_stream_hidden_dragon.SingleStreamRealTimeEngine'
        """
        return cls._VNPY_STRATEGIES.get(strategy_key)
    
    @classmethod
    def register_vnpy_strategy(cls, strategy_key: str, engine_class_path: str):
        """
        Register a new vnpy strategy (useful for plugins/extensions).
        
        Args:
            strategy_key: User-facing strategy identifier
            engine_class_path: Full path to engine class
        """
        cls._VNPY_STRATEGIES[strategy_key] = engine_class_path
    
    @classmethod
    def list_vnpy_strategies(cls) -> Dict[str, str]:
        """Get all registered vnpy strategies."""
        return cls._VNPY_STRATEGIES.copy()
    
    @classmethod
    def is_valid_strategy(cls, strategy_key: str) -> bool:
        """Check if a strategy key is registered."""
        return strategy_key in cls._VNPY_STRATEGIES


# Convenience function for direct use
def get_engine_class_for_strategy(strategy_key: str, engine: str = "vnpy") -> Optional[str]:
    """
    Get engine class path for a strategy.
    
    Args:
        strategy_key: Strategy identifier (e.g., 'hidden_dragon')
        engine: Engine type (default: 'vnpy')
        
    Returns:
        Engine class path or None
        
    Example:
        >>> get_engine_class_for_strategy('hidden_dragon')
        'scripts.single_stream_hidden_dragon.SingleStreamRealTimeEngine'
    """
    if engine == "vnpy":
        return StrategyRegistry.get_vnpy_engine_class(strategy_key)
    # Future: add support for other engines (backtrader, etc.)
    return None
