import json
from pathlib import Path

from django.core.management.base import BaseCommand

from flowgic.api import api


class Command(BaseCommand):
    help = 'Export a deterministic OpenAPI snapshot for frontend client generation.'

    def add_arguments(self, parser):
        parser.add_argument('--output', default='openapi.json')

    def handle(self, *args, **options):
        schema = api.get_openapi_schema(path_prefix='/api/')
        path = Path(options['output'])
        path.write_text(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'OpenAPI exported to {path}'))
