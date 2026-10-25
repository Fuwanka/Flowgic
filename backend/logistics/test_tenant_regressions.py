import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from .forms import OrderEditForm, OrderForm
from .models import Financial, Order

pytestmark = pytest.mark.integration


def test_foreign_order_detail_has_no_financial_side_effect(authenticated_client, order_b):
    response = authenticated_client.get(reverse('request_detail', args=[order_b.pk]))
    assert response.status_code == 404
    assert not Financial.objects.filter(order=order_b).exists()


def test_foreign_order_cannot_be_updated(authenticated_client, order_b):
    response = authenticated_client.post(
        reverse('update_order_status', args=[order_b.pk]),
        data='{"status":"completed"}', content_type='application/json',
    )
    assert response.status_code == 404
    order_b.refresh_from_db()
    assert order_b.status == Order.Status.CREATED


def test_driver_cannot_open_order_creation(driver_client):
    response = driver_client.get(reverse('new_request'))
    assert response.status_code == 403


@pytest.mark.parametrize('form_class', [OrderForm, OrderEditForm])
def test_order_resource_choices_are_tenant_scoped(
    db, form_class, dispatcher_a, driver_a, driver_b, vehicle_a, vehicle_b,
):
    form = form_class(user=dispatcher_a)
    assert list(form.fields['driver'].queryset) == [driver_a]
    assert list(form.fields['vehicle'].queryset) == [vehicle_a]
    # Posted IDs are validated against these querysets by ModelChoiceField.
    with pytest.raises(ValidationError) as error:
        form.fields['driver'].clean(str(driver_b.pk))
    assert error.value.code == 'invalid_choice'
    with pytest.raises(ValidationError) as error:
        form.fields['vehicle'].clean(str(vehicle_b.pk))
    assert error.value.code == 'invalid_choice'


def test_calendar_does_not_expose_other_company(authenticated_client, order_a, order_b):
    response = authenticated_client.get(reverse('calendar'))
    assert response.status_code == 200
    events = response.context['events_json']
    assert order_a.order_number in events
    assert order_b.order_number not in events


@pytest.mark.parametrize('route,foreign_fixture', [
    ('client_detail', 'client_b'),
    ('vehicle_detail', 'vehicle_b'),
    ('driver_detail', 'driver_b'),
])
def test_foreign_directory_record_is_hidden(authenticated_client, request, route, foreign_fixture):
    record = request.getfixturevalue(foreign_fixture)
    response = authenticated_client.get(reverse(route, args=[record.pk]))
    assert response.status_code == 404
