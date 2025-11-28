# training/forms.py
from django import forms
from django.forms.widgets import ClearableFileInput

from .models import ModelType, BaseModel, ModelArtifact


class MultiFileInput(ClearableFileInput):
    """Widget that allows selecting multiple files."""
    allow_multiple_selected = True


class MultiFileField(forms.FileField):
    """
    FileField без стандартной проверки "No file was submitted".
    Мы сами валидируем файлы в form.clean().
    """
    widget = MultiFileInput

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("required", False)  # не требуем на уровне поля
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        # Не трогаем data, не вызываем стандартную FileField.clean,
        # просто возвращаем то, что нам дали.
        # Настоящая валидация делаетcя в TrainingJobCreateForm.clean().
        return data


class TrainingJobCreateForm(forms.Form):
    """
    Форма для создания заказа на обучение модели.
    Пользователь выбирает тип модели, базовую модель, имя проекта и загружает фото.
    """

    project_name = forms.CharField(
        max_length=100,
        label="Project name",
        help_text="For example: rin_vtuber_v1",
    )

    model_type = forms.ModelChoiceField(
        queryset=ModelType.objects.filter(is_active=True),
        label="Model type",
        empty_label=None,
    )

    base_model = forms.ModelChoiceField(
        queryset=BaseModel.objects.filter(is_active=True),
        label="Base model",
        empty_label=None,
    )

    images = MultiFileField(
        label="Training images",
        help_text="Upload between 10 and 60 images.",
    )

    MIN_IMAGES = 10
    MAX_IMAGES = 60
    ALLOWED_CONTENT_TYPES = ("image/jpeg", "image/png", "image/webp")

    def clean(self):
        """
        Общая валидация формы: проверяем файлы вручную.
        """
        cleaned_data = super().clean()

        # Все реально загруженные файлы приходят в self.files, а не в cleaned_data
        files = self.files.getlist("images")

        if len(files) < self.MIN_IMAGES:
            self.add_error(
                "images",
                forms.ValidationError(
                    f"Please upload at least {self.MIN_IMAGES} images."
                ),
            )
        elif len(files) > self.MAX_IMAGES:
            self.add_error(
                "images",
                forms.ValidationError(
                    f"Please upload no more than {self.MAX_IMAGES} images."
                ),
            )
        else:
            for f in files:
                if f.content_type not in self.ALLOWED_CONTENT_TYPES:
                    self.add_error(
                        "images",
                        forms.ValidationError(
                            "Only JPEG, PNG and WEBP images are allowed."
                        ),
                    )
                    break

        # Если есть ошибки по images — не пишем файлы в cleaned_data
        if "images" in self.errors:
            return cleaned_data

        # Всё ок — кладём список файлов в cleaned_data["images"],
        # чтобы view мог их забрать.
        cleaned_data["images"] = files
        return cleaned_data


class ModelArtifactForm(forms.ModelForm):
    """Form for staff to attach a trained model to a job."""

    class Meta:
        model = ModelArtifact
        fields = ["file", "download_url", "size_mb"]

    def clean(self):
        cleaned_data = super().clean()
        file = cleaned_data.get("file")
        download_url = cleaned_data.get("download_url")

        if not file and not download_url:
            raise forms.ValidationError(
                "Upload a model file or provide a download URL."
            )

        return cleaned_data
