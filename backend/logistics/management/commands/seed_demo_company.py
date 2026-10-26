import os

from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError

from accounts.exceptions import AccountError
from logistics.demo import seed_demo_company
from marketplace.exceptions import MarketplaceError


class Command(BaseCommand):
    help = 'Создаёт изолированную демо-компанию. Повторный запуск сохраняет данные и пароли.'

    def add_arguments(self, parser):
        parser.add_argument('--slug', default='flowgic-demo')
        parser.add_argument('--name', default='Flowgic · Демо-перевозки')
        parser.add_argument('--orders', type=int, default=12)
        parser.add_argument('--plan', choices=['FREE', 'PRO', 'ENTERPRISE'], default=None)
        parser.add_argument('--password-env', default=None, metavar='ENVIRONMENT_VARIABLE')

    def handle(self, *args, **options):
        variable = options['password_env']
        password = os.environ.get(variable) if variable else None
        if variable and not password:
            raise CommandError('Переменная окружения с паролем не задана или пуста.')
        try:
            result = seed_demo_company(
                slug=options['slug'], name=options['name'], orders=options['orders'],
                plan_type=options['plan'], password=password,
            )
        except (ValueError, AccountError, MarketplaceError, IntegrityError) as error:
            # Do not expose DB rows or supplied credentials in command output.
            message = str(error) if not isinstance(error, IntegrityError) else 'Конфликт идентификаторов. Изменения отменены.'
            raise CommandError(message) from error
        self.stdout.write(self.style.SUCCESS(
            f'{"Создана" if result.created else "Уже существует"}: {result.company.name} ({result.company.pk})'
        ))
        self.stdout.write('\n'.join(result.login_emails))
        if result.generated_password:
            self.stdout.write(f'Одноразовый вывод общего демо-пароля: {result.generated_password}')
        elif result.created:
            self.stdout.write('Пароль взят из указанной переменной окружения.')
        else:
            self.stdout.write('Данные и пароли сохранены.')
