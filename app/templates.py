import os
from fastapi.templating import Jinja2Templates

# Path to the templates directory
TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")

# Expose templates utility
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Add custom filter for formatting views count
def format_views(val) -> str:
    try:
        val = int(val)
        if val >= 1_000_000:
            return f"{val/1_000_000:.1f}M"
        elif val >= 1_000:
            return f"{val/1_000:.1f}K"
        return str(val)
    except (ValueError, TypeError):
        return str(val)

# Add custom filter for currency formatting
def format_currency(val) -> str:
    try:
        val = float(val)
        return f"${val:,.2f}"
    except (ValueError, TypeError):
        return f"${val}"

# Register custom template filters
templates.env.filters["format_views"] = format_views
templates.env.filters["format_currency"] = format_currency
