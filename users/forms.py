
from django import forms
from .models import CarreraManual, LactatoManual, Perfil, Grupo, Ritmo, EntrenamientoDiario, EntrenamientoRecurso
from django.contrib.auth.models import User


def _resolve_form_user_club(user):
    try:
        perfil = getattr(user, "perfil", None)
        if perfil:
            if getattr(perfil, "club", None):
                return perfil.club
            grupo = getattr(perfil, "grupo", None)
            if grupo and getattr(grupo, "club", None):
                return grupo.club
    except Exception:
        return None
    return None


def _scope_grupo_field(form, user=None, user_club=None):
    if user_club is None and user is not None:
        user_club = _resolve_form_user_club(user)

    if user_club:
        form.fields["grupo"].queryset = Grupo.objects.filter(club=user_club).order_by("nombre")
    elif user is not None and user.is_superuser:
        form.fields["grupo"].queryset = Grupo.objects.select_related("club").order_by("nombre")
    else:
        form.fields["grupo"].queryset = Grupo.objects.none()


# Formulario para agregar/editar carreras manuales
class CarreraManualForm(forms.ModelForm):
    class Meta:
        model = CarreraManual
        fields = ["fecha", "distancia_m", "tiempo"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date", "onclick": "if (this.showPicker) this.showPicker()"}, format="%Y-%m-%d"),
            "tiempo": forms.TextInput(attrs={"placeholder": "mm:ss o hh:mm:ss"}),
        }


class LactatoManualForm(forms.ModelForm):
    class Meta:
        model = LactatoManual
        fields = ["fecha", "umbral_lactato", "ritmo"]
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date", "onclick": "if (this.showPicker) this.showPicker()"}, format="%Y-%m-%d"),
            "umbral_lactato": forms.TextInput(attrs={"placeholder": "Ej: 4.0", "inputmode": "decimal"}),
            "ritmo": forms.TextInput(attrs={"placeholder": "Ej: 4:15 /km"}),
        }


class CrearCorredorForm(forms.Form):
    username = forms.CharField(max_length=150, label="Nombre de usuario")
    first_name = forms.CharField(max_length=150, required=False, label="Nombre")
    last_name = forms.CharField(max_length=150, required=False, label="Apellido")
    fecha_nacimiento = forms.DateField(
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date", "onclick": "if (this.showPicker) this.showPicker()"}, format="%Y-%m-%d"),
        label="Fecha de nacimiento",
    )
    email = forms.EmailField(required=False, label="Correo")
    grupo = forms.ModelChoiceField(queryset=Grupo.objects.all(), required=False, label="Grupo")
    meta_actual = forms.CharField(max_length=200, required=False, label="Meta actual")
    mejor_marca = forms.CharField(max_length=200, required=False, label="Mejor marca")
    modalidad_ritmo = forms.ChoiceField(
        choices=Perfil.MODALIDAD_RITMO_CHOICES,
        required=True,
        label="Modalidad de ritmos",
        initial="runners",
    )

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Ese nombre de usuario ya existe.")
        return username

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        user_club = kwargs.pop("user_club", None)
        super().__init__(*args, **kwargs)
        _scope_grupo_field(self, user=user, user_club=user_club)


class EditarCorredorForm(forms.Form):
    first_name = forms.CharField(max_length=150, required=False, label="Nombre")
    last_name = forms.CharField(max_length=150, required=False, label="Apellido")
    fecha_nacimiento = forms.DateField(
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date", "onclick": "if (this.showPicker) this.showPicker()"}, format="%Y-%m-%d"),
        label="Fecha de nacimiento",
    )
    email = forms.EmailField(required=False, label="Correo")
    grupo = forms.ModelChoiceField(queryset=Grupo.objects.all(), required=False, label="Grupo")
    meta_actual = forms.CharField(max_length=200, required=False, label="Meta actual")
    mejor_marca = forms.CharField(max_length=200, required=False, label="Mejor marca")
    modalidad_ritmo = forms.ChoiceField(
        choices=Perfil.MODALIDAD_RITMO_CHOICES,
        required=True,
        label="Modalidad de ritmos",
    )

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        user_club = kwargs.pop("user_club", None)
        super().__init__(*args, **kwargs)
        _scope_grupo_field(self, user=user, user_club=user_club)


class RitmoForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # HTML5 date inputs require YYYY-MM-DD to display existing value.
        self.fields["fecha"].input_formats = ["%Y-%m-%d"]

    class Meta:
        model = Ritmo
        exclude = ("usuario", "creado_en", "tipo")
        widgets = {
            "fecha": forms.DateInput(attrs={"type": "date", "onclick": "if (this.showPicker) this.showPicker()"}, format="%Y-%m-%d"),
        }


class GrupoForm(forms.ModelForm):
    class Meta:
        model = Grupo
        fields = ["nombre", "descripcion"]
        widgets = {
            "nombre": forms.TextInput(attrs={"placeholder": "Ej: 10K, 5K, Intermedio"}),
            "descripcion": forms.Textarea(attrs={"rows": 3, "placeholder": "Descripción opcional del grupo"}),
        }


class EntrenamientoDiarioForm(forms.ModelForm):
    class Meta:
        model = EntrenamientoDiario
        fields = ["modalidad", "tipo", "titulo", "descripcion"]
        widgets = {
            "descripcion": forms.Textarea(attrs={"rows": 4}),
        }


class EntrenamientoRecursoForm(forms.ModelForm):
    class Meta:
        model = EntrenamientoRecurso
        fields = ["titulo", "url", "tipo", "orden"]
        widgets = {
            "titulo": forms.TextInput(attrs={"placeholder": "Ej: CORE 12 min - Estabilidad"}),
            "url": forms.URLInput(attrs={"placeholder": "https://drive.google.com/..."}),
            "orden": forms.NumberInput(attrs={"min": "1"}),
        }
