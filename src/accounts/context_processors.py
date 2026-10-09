def theme_context(request):
    """
    Context processor providing current_theme for templates.
    Checks:
    1. Authenticated user's preference in database
    2. Cookie 'flowgic_theme'
    3. Default to 'light'
    """
    current_theme = 'light'
    if request.user.is_authenticated and hasattr(request.user, 'theme') and request.user.theme:
        current_theme = request.user.theme
    else:
        current_theme = request.COOKIES.get('flowgic_theme', 'light')

    if current_theme not in ('light', 'dark'):
        current_theme = 'light'

    return {
        'current_theme': current_theme
    }
