# Comprehensive Test Suite - README

## Overview

This test suite provides comprehensive testing for the Flowgic logistics application, including:
- **Unit tests**: 35+ tests for models and business logic
- **Integration tests**: 30+ tests for data isolation and view workflows
- **E2E tests**: 25+ tests for complete user workflows

**Total: 90+ tests**

## Test Structure

```
src/
├── conftest.py                              # Shared fixtures for all tests
├── logistics/
│   ├── tests.py                             # Unit tests for logistics models
│   ├── test_data_isolation.py               # Multi-tenancy isolation tests
│   ├── test_views_integration.py            # View workflow integration tests
│   ├── test_order_creation_e2e.py           # Order lifecycle E2E tests
│   ├── test_payment_workflow_e2e.py         # Payment workflow E2E tests
│   ├── test_dashboards_e2e.py               # Dashboard functionality E2E tests
│   └── factories.py                         # Test data factories
└── accounts/
    └── tests.py                             # Unit tests for user models
```

## Running Tests

### Run All Tests
```bash
# Using Django test runner
python src/manage.py test

# Using pytest (recommended)
pytest src/

# With verbose output
pytest src/ -v
```

### Run by Category

```bash
# Unit tests only
pytest src/ -m unit

# Integration tests only
pytest src/ -m integration

# E2E tests only
pytest src/ -m e2e

# Exclude slow tests
pytest src/ -m "not slow"
```

### Run Specific Test Files

```bash
# Financial unit tests
python src/manage.py test logistics.tests

# Data isolation tests
python src/manage.py test logistics.test_data_isolation

# Payment workflow tests
python src/manage.py test logistics.test_payment_workflow_e2e

# All logistics tests
python src/manage.py test logistics

# User model tests
python src/manage.py test accounts.tests
```

### Run with Coverage

```bash
# Install coverage first
pip install coverage

# Run tests with coverage
coverage run --source='src' src/manage.py test

# View coverage report
coverage report

# Generate HTML coverage report
coverage html
# Open htmlcov/index.html in browser
```

## Test Categories

### Unit Tests (35+ tests)

**Financial Operations** (`logistics/tests.py`)
- ✅ Profit calculation with various cost combinations
- ✅ Automatic fuel expense calculation based on distance  
- ✅ Payment status transitions (unpaid → partially paid → paid)
- ✅ Third-party cost handling
- ✅ Negative profit scenarios
- ✅ Financial record one-to-one relationship with orders

**Model Logic** (`logistics/tests.py`, `accounts/tests.py`)
- ✅ Order creation, status transitions, properties
- ✅ Vehicle status changes, unique constraints
- ✅ Client and company model behavior
- ✅ User roles, status transitions, authentication
- ✅ Password reset code validation
- ✅ OrderEvent creation and logging

### Integration Tests (30+ tests)

**Data Isolation** (`logistics/test_data_isolation.py`)
- ✅ Company data boundaries (orders, clients, vehicles)
- ✅ Dashboard filtering by company
- ✅ Order detail access control
- ✅ Client and vehicle list filtering
- ✅ Role-based access control (dispatcher, driver, manager)

**View Workflows** (`logistics/test_views_integration.py`)
- ✅ Payment update workflows
- ✅ Order status change workflows
- ✅ Financial data updates with profit recalculation
- ✅ OrderEvent logging for all operations
- ✅ Permission enforcement (drivers vs dispatchers)

### E2E Tests (25+ tests)

**Order Lifecycle** (`logistics/test_order_creation_e2e.py`)
- ✅ Complete order creation workflow
- ✅ Driver and vehicle assignment
- ✅ Status progression (created → completed)
- ✅ Order cancellation
- ✅ Delay handling scenarios

**Payment Workflows** (`logistics/test_payment_workflow_e2e.py`)
- ✅ Partial payment tracking
- ✅ Full payment workflows
- ✅ Payment history with multiple events
- ✅ Set total amount payments
- ✅ Integration with order completion

**Dashboards** (`logistics/test_dashboards_e2e.py`)
- ✅ Dispatcher dashboard (all company orders, filtering)
- ✅ Driver dashboard (assigned orders only)
- ✅ Manager dashboard (statistics, full visibility)
- ✅ Calendar view (scheduled orders)
- ✅ Performance with large datasets

## Test Fixtures

The test suite uses pytest fixtures defined in `src/conftest.py`:

### Company & User Fixtures
- `company_a`, `company_b` - Two separate companies for isolation testing
- `dispatcher_a`, `dispatcher_b` - Dispatchers for each company
- `manager_a` - Manager for company A
- `driver_a`, `driver_b` - Drivers for each company

### Business Data Fixtures
- `client_a`, `client_b` - Clients for each company
- `vehicle_a`, `vehicle_b` - Vehicles for each company
- `order_a`, `order_b` - Sample orders for each company
- `financial_a` - Financial record for order A

### Authentication Fixtures
- `authenticated_client` - Test client logged in as dispatcher A
- `driver_client` - Test client logged in as driver A
- `manager_client` - Test client logged in as manager A

## Factory Classes

Use factories in `logistics/factories.py` for flexible test data generation:

```python
from logistics.factories import OrderFactory, FinancialFactory

# Create order with defaults
order = OrderFactory.create()

# Create order with specific company
order = OrderFactory.create(client__company=my_company)

# Create multiple orders
orders = [OrderFactory.create() for _ in range(10)]

# Create financial record
financial = FinancialFactory.create(order=order)
```

## Continuous Integration

For CI/CD pipelines, use:

```bash
# Run all tests with coverage and generate XML report
coverage run --source='src' src/manage.py test
coverage xml

# Or with pytest
pytest src/ --cov=src --cov-report=xml --cov-report=term
```

## Troubleshooting

### Database Issues
- Tests use Django's test database (auto-created and destroyed)
- If tests fail to clean up: `python src/manage.py flush --noinput`

### Migration Issues
- Ensure migrations are up to date: `python src/manage.py migrate`
- pytest uses `--nomigrations` flag for speed

### Import Errors
- Ensure `DJANGO_SETTINGS_MODULE` is set: `set DJANGO_SETTINGS_MODULE=src.flowgic.settings`
- Or use pytest which automatically configures this via `pytest.ini`

## Expected Coverage

Target coverage by module:
- `logistics/models.py`: 85%+
- `logistics/views.py`: 75%+
- `accounts/models.py`: 90%+
- Overall: 80%+

## Next Steps

To extend the test suite:

1. **Browser-based E2E tests** - Use Selenium/Playwright for UI testing
2. **Performance tests** - Add load testing for high-traffic scenarios
3. **API tests** - If REST API is added, include endpoint tests
4. **Security tests** - Add authentication bypass and injection tests
