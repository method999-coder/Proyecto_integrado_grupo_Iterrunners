def roles(request):
    user = request.user
    if not user.is_authenticated:
        return {
            "es_corredor": False,
            "es_profesor": False,
            "es_admin": False,
        }

    return {
        "es_corredor": user.groups.filter(name="Corredor").exists(),
        "es_profesor": user.groups.filter(name="Profesor").exists(),
        "es_admin": user.groups.filter(name="Admin").exists(),
    }
