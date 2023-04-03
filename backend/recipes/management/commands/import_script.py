from django.core.management.base import BaseCommand
from recipes import models


class Command(BaseCommand):
    def handle(self, **options):
        with open('/home/sas/foodgram-project-react'
                  '/data/ingredients.csv') as csv:
            for line in csv:
                value = line.split(',')
                models.Ingredient.objects.get_or_create(
                    name=value[0],
                    measurement_unit=value[1]
                )
