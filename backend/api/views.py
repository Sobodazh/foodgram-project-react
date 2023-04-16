from datetime import datetime

from django.contrib.auth import get_user_model
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from djoser.views import UserViewSet
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import (SAFE_METHODS, IsAuthenticated,
                                        IsAuthenticatedOrReadOnly)
from rest_framework.response import Response
from rest_framework.status import HTTP_400_BAD_REQUEST
from rest_framework.viewsets import ModelViewSet, ReadOnlyModelViewSet

from recipes.models import (Favorite, Ingredient, IngredientInRecipe, Recipe,
                            ShoppingCart, Tag)
from users.models import Follow

from .filters import IngredientFilter, RecipeFilter
from .pagination import CustomPagination
from .permissions import IsAuthorOrReadOnly
from .serializers import (CustomUserSerializer, FollowSerializer,
                          IngredientSerializer, RecipeCutSerializer,
                          RecipeReadSerializer, RecipeWriteSerializer,
                          TagSerializer)

User = get_user_model()


class CustomUserViewSet(UserViewSet):
    queryset = User.objects.all()
    serializer_class = CustomUserSerializer
    pagination_class = CustomPagination
    permission_classes = (IsAuthenticatedOrReadOnly,)

    @action(
        detail=True,
        methods=['post', 'delete'],
        permission_classes=[IsAuthenticated]
    )
    def subscribe(self, request, **kwargs):
        current_user = request.user
        author_id = self.kwargs.get('id')
        author = get_object_or_404(User, id=author_id)

        if request.method == 'POST':
            serializer = FollowSerializer(author,
                                          data=request.data,
                                          context={"request": request})
            serializer.is_valid(raise_exception=True)
            Follow.objects.create(user=current_user, author=author)
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        elif request.method == 'DELETE':
            subscription = get_object_or_404(Follow,
                                             user=current_user,
                                             author=author)
            subscription.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

    @action(
        detail=False,
        permission_classes=[IsAuthenticated]
    )
    def subscriptions(self, request):
        current_user = request.user
        queryset = User.objects.filter(following__user=current_user)
        pages = self.paginate_queryset(queryset)
        serializer = FollowSerializer(pages,
                                      many=True,
                                      context={'request': request})
        return self.get_paginated_response(serializer.data)


class IngredientViewSet(ReadOnlyModelViewSet):
    queryset = Ingredient.objects.all()
    serializer_class = IngredientSerializer
    filter_backends = (DjangoFilterBackend,)
    filterset_class = IngredientFilter
    pagination_class = None


class TagViewSet(ReadOnlyModelViewSet):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    permission_classes = (IsAuthenticatedOrReadOnly,)
    pagination_class = None


class RecipeViewSet(ModelViewSet):
    queryset = Recipe.objects.all()
    permission_classes = (IsAuthorOrReadOnly,)
    pagination_class = CustomPagination
    filter_backends = (DjangoFilterBackend,)
    filterset_class = RecipeFilter

    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

    def get_serializer_class(self):
        if self.request.method in SAFE_METHODS:
            return RecipeReadSerializer
        return RecipeWriteSerializer

    @action(
        detail=True,
        methods=['post', 'delete'],
        permission_classes=[IsAuthenticated]
    )
    def favorite(self, request, pk):
        if request.method == 'POST':
            return self.add_to(Favorite, request.user, pk)
        elif request.method == 'DELETE':
            return self.delete_from(Favorite, request.user, pk)

    @action(detail=True,
            methods=['post', 'delete'],
            permission_classes=[IsAuthenticated])
    def shopping_cart(self, request, pk):
        if request.method == 'POST':
            return self.add_to(ShoppingCart, request.user, pk)
        elif request.method == 'DELETE':
            return self.delete_from(ShoppingCart, request.user, pk)

    def add_to(self, model, user, pk):
        if model.objects.filter(user=user, recipe__id=pk).exists():
            return Response({'errors': 'Этот рецепт уже добавлен'},
                            status=status.HTTP_400_BAD_REQUEST)
        recipe = get_object_or_404(Recipe, id=pk)
        model.objects.create(user=user, recipe=recipe)
        serializer = RecipeCutSerializer(recipe)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def delete_from(self, model, user, pk):
        value = model.objects.filter(user=user, recipe__id=pk)
        if value.exists():
            value.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({'errors': 'Рецепт был удален'},
                        status=status.HTTP_400_BAD_REQUEST)

    @action(
        detail=False,
        permission_classes=[IsAuthenticated]
    )
    def download_shopping_cart(self, request):
        current_user = request.user
        if not current_user.shopping_cart.exists():
            return Response(status=HTTP_400_BAD_REQUEST)

        ingredients = IngredientInRecipe.objects.filter(
            recipe__shopping_cart__user=request.user
        ).values(
            'ingredient__name',
            'ingredient__measurement_unit'
        ).annotate(amount=Sum('amount'))

        today = datetime.today()
        shopping_list = (
            f'Список покупок для: {current_user.get_full_name()}\n'
            f'Дата: {today:%Y-%m-%d}\n'
        )
        shopping_list += '\n'.join([
            f'- {ingredient["ingredient__name"]} '
            f'- {ingredient["ingredient__measurement_unit"]}'
            f'- {ingredient["amount"]}'
            for ingredient in ingredients
        ])
        shopping_list += f'\n ({today:%Y})'

        filename = f'{current_user.username}_shopping_list.txt'
        response = HttpResponse(shopping_list, content_type='text/plain')
        response['Content-Disposition'] = f'attachment; filename={filename}'

        return response
