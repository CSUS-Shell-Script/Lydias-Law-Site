from functools import wraps
from django.core.exceptions import PermissionDenied

def superuser_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        user = request.user
        allowed = (
            user.is_authenticated
            and ( user.is_superuser or user.is_staff or getattr(user, "role", None) == "ADMIN" )
        )
        if not allowed:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)
    return _wrapped_view