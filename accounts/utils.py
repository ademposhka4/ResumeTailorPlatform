"""
Accounts app utility functions

Helper functions for token management and user operations.
"""


def check_and_increment_tokens(user, cost: int = 1):
    """
    Check if user has enough tokens and increment usage.
    
    Args:
        user: User instance
        cost: Number of tokens to consume
    
    Raises:
        PermissionError: If user exceeds token quota
    """
    if user.tokens_used + cost > user.token_quota:
        raise PermissionError("Token quota exceeded.")
    
    user.tokens_used += cost
    user.save(update_fields=['tokens_used'])
