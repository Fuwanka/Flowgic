// request_detail.js - Обработка обновления статуса и финансов заказа

document.addEventListener('DOMContentLoaded', function() {
    // Обработка изменения статуса
    const statusSelect = document.getElementById('status-select');
    const statusMessage = document.getElementById('status-message');
    const orderStatusBadge = document.getElementById('order-status-badge');

    if (statusSelect) {
        statusSelect.addEventListener('change', function() {
            const newStatus = this.value;
            if (!newStatus) return;

            // Получаем CSRF токен
            const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

            // Отправляем AJAX запрос
            fetch(window.location.pathname + 'status/', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-CSRFToken': csrfToken
                },
                body: new URLSearchParams({
                    'status': newStatus
                })
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Обновляем бейдж статуса
                    orderStatusBadge.textContent = data.status_display;
                    orderStatusBadge.className = `status-badge status-${data.status}`;

                    // Показываем сообщение об успехе
                    statusMessage.textContent = 'Статус обновлён успешно';
                    statusMessage.style.color = 'green';
                    statusMessage.style.display = 'block';

                    // Сбрасываем селект
                    statusSelect.value = '';

                    // Скрываем сообщение через 3 секунды
                    setTimeout(() => {
                        statusMessage.style.display = 'none';
                    }, 3000);
                } else {
                    // Показываем ошибку
                    statusMessage.textContent = data.error || 'Ошибка обновления статуса';
                    statusMessage.style.color = 'red';
                    statusMessage.style.display = 'block';
                }
            })
            .catch(error => {
                console.error('Error:', error);
                statusMessage.textContent = 'Ошибка сети';
                statusMessage.style.color = 'red';
                statusMessage.style.display = 'block';
            });
        });
    }

    // Обработка формы финансов
    const financialForm = document.getElementById('financial-form');
    const financialMessage = document.getElementById('financial-message');
    const profitDisplay = document.getElementById('profit-display');

    if (financialForm) {
        financialForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const formData = new FormData();
            formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);
            formData.append('fuel_expenses', document.getElementById('id_fuel_expenses').value);
            formData.append('driver_cost', document.getElementById('id_driver_cost').value);

            fetch(window.location.pathname + 'update-financials/', {
                method: 'POST',
                body: formData
            })
            .then(response => response.json())
            .then(data => {
                if (data.success) {
                    // Обновляем отображение прибыли
                    profitDisplay.textContent = data.profit;

                    // Показываем сообщение об успехе
                    financialMessage.textContent = 'Финансы обновлены успешно';
                    financialMessage.style.color = 'green';
                    financialMessage.style.display = 'block';

                    // Скрываем сообщение через 3 секунды
                    setTimeout(() => {
                        financialMessage.style.display = 'none';
                    }, 3000);
                } else {
                    // Показываем ошибку
                    financialMessage.textContent = data.error || 'Ошибка обновления финансов';
                    financialMessage.style.color = 'red';
                    financialMessage.style.display = 'block';
                }
            })
            .catch(error => {
                console.error('Error:', error);
                financialMessage.textContent = 'Ошибка сети';
                financialMessage.style.color = 'red';
                financialMessage.style.display = 'block';
            });
        });
    }
});
