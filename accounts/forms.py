# accounts/forms.py
from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm

User = get_user_model()


class UserRegistrationForm(UserCreationForm):
    """
    Регистрация по email.
    username мы используем как email под капотом.
    """
    username = forms.EmailField(
        label="Email",
        required=True,
        help_text="We'll send a confirmation link to this address.",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username",)  # только email

    def save(self, commit=True):
        user = super().save(commit=False)
        email = self.cleaned_data["username"]
        user.username = email
        user.email = email
        user.is_active = False  # до подтверждения
        if commit:
            user.save()
        return user


class EmailAuthenticationForm(AuthenticationForm):
    """
    Логин по email (на самом деле всё тот же username, просто поле называется Email).
    """
    username = forms.EmailField(label="Email", required=True)
