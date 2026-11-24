from io import BytesIO
import uuid
import warnings

from django import forms
from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

from .models import GravePhoto

MAX_BYTES = 5 * 1024 * 1024
MAX_PIXELS = 20_000_000


class GravePhotoForm(forms.ModelForm):
    # Decode ourselves rather than relying on the filename or browser MIME type.
    image = forms.FileField(label="Zdjęcie", help_text="JPEG lub PNG, do 5 MB i 20 megapikseli.",
                            widget=forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png"}))

    class Meta:
        model = GravePhoto
        fields = ("image", "caption")

    def clean_image(self):
        upload = self.cleaned_data["image"]
        if upload.size > MAX_BYTES:
            raise forms.ValidationError("Zdjęcie nie może przekraczać 5 MB.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(upload) as image:
                    fmt = image.format
                    if fmt not in ("JPEG", "PNG") or getattr(image, "n_frames", 1) != 1:
                        raise ValueError
                    if image.width * image.height > MAX_PIXELS:
                        raise ValueError
                    image.verify()
                upload.seek(0)
                with Image.open(upload) as image:
                    image.load()
                    # Copy pixels into a fresh image: EXIF, text and profiles are discarded.
                    mode = "RGBA" if fmt == "PNG" else "RGB"
                    clean = Image.new(mode, image.size)
                    clean.paste(image.convert(mode))
                    output = BytesIO()
                    clean.save(output, format=fmt)
            extension = "jpg" if fmt == "JPEG" else "png"
            return ContentFile(output.getvalue(), name=f"{uuid.uuid4().hex}.{extension}")
        except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise forms.ValidationError("Wybierz poprawne, nieruchome zdjęcie JPEG lub PNG do 20 megapikseli.")
