class EdgefulError(Exception):
    """Base exception for Edgeful client failures."""


class ConfigurationError(EdgefulError):
    """Raised when the client configuration is invalid."""


class ApiError(EdgefulError):
    """Raised when the Edgeful API returns an error response."""


class AuthenticationError(ApiError):
    """Raised when Edgeful rejects the API key."""


class EntitlementError(ApiError):
    """Raised when the API key lacks access to a resource."""


class RateLimitError(ApiError):
    """Raised when Edgeful keeps rate limiting the request."""


class ResponseFormatError(ApiError):
    """Raised when Edgeful returns an unexpected response shape."""
