from rest_framework import serializers, viewsets
from rest_framework.exceptions import ValidationError
from .forms import SearchForm, search_deceased
from .models import Burial, Cemetery, Deceased, Grave


class CemeterySerializer(serializers.ModelSerializer):
    class Meta:
        model = Cemetery
        fields = ("id", "name", "address")


class GraveSerializer(serializers.ModelSerializer):
    cemetery = CemeterySerializer(source="section.cemetery", read_only=True)
    section = serializers.CharField(source="section.name", read_only=True)

    class Meta:
        model = Grave
        fields = ("id", "cemetery", "section", "row", "number")


class BurialSerializer(serializers.ModelSerializer):
    grave = GraveSerializer(read_only=True)

    class Meta:
        model = Burial
        fields = ("id", "burial_date", "grave")


class DeceasedSerializer(serializers.ModelSerializer):
    burials = BurialSerializer(many=True, read_only=True)

    class Meta:
        model = Deceased
        fields = ("id", "name", "surname", "birth_date", "death_date", "burials")


class CemeteryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Cemetery.objects.all()
    serializer_class = CemeterySerializer


class GraveViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Grave.objects.select_related("section__cemetery")
    serializer_class = GraveSerializer


class DeceasedViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = DeceasedSerializer

    def get_queryset(self):
        form = SearchForm(self.request.query_params)
        if not form.is_valid():
            raise ValidationError(
                {key: list(value) for key, value in form.errors.items()}
            )
        return search_deceased(form.cleaned_data)
