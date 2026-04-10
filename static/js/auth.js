// Конфигурация
const AUTH_API_URL = '';

// DOM элементы
let authElements = {};

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    initAuthElements();
    attachAuthEventListeners();
    checkAuth();
});

function initAuthElements() {
    authElements = {
        tabs: document.querySelectorAll('.auth-tab'),
        loginForm: document.getElementById('login-form'),
        registerForm: document.getElementById('register-form'),
        resetForm: document.getElementById('reset-form'),
        loginFormElement: document.getElementById('login-form-element'),
        registerFormElement: document.getElementById('register-form-element'),
        resetFormElement: document.getElementById('reset-form-element'),
        messageDiv: document.getElementById('auth-message'),
        userInfo: document.getElementById('user-info'),
        userEmail: document.getElementById('user-email'),
        tabsContainer: document.getElementById('auth-tabs')
    };
}

function attachAuthEventListeners() {
    // Переключение между вкладками
    authElements.tabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;
            switchAuthTab(tabName);
        });
    });
    
    // Обработчики форм
    if (authElements.loginFormElement) {
        authElements.loginFormElement.addEventListener('submit', handleLogin);
    }
    
    if (authElements.registerFormElement) {
        authElements.registerFormElement.addEventListener('submit', handleRegister);
    }
     if (authElements.resetFormElement) {
        authElements.resetFormElement.addEventListener('submit', handleResetPassword);
     }
}

function switchAuthTab(tabName) {
    // Обновляем активные вкладки
    authElements.tabs.forEach(tab => {
        if (tab.dataset.tab === tabName) {
            tab.classList.add('active');
        } else {
            tab.classList.remove('active');
        }
    });
    
    // показываем нужную форму
        authElements.loginForm.classList.remove('active');
        authElements.registerForm.classList.remove('active');
        authElements.resetForm.classList.remove('active');

    if (tabName === 'login') {
        authElements.loginForm.classList.add('active');
    } else if (tabName === 'register') {
        authElements.registerForm.classList.add('active');
    } else if (tabName === 'reset') {
        authElements.resetForm.classList.add('active');
    }
    
    // Очищаем сообщения
    hideAuthMessage();
}

async function handleResetPassword(event) {
    event.preventDefault();
    
    const email = document.getElementById('reset-email').value;
    const newPassword = document.getElementById('reset-new-password').value;
    const confirmPassword = document.getElementById('reset-confirm-password').value;
    
    // Проверяем, что пароли совпадают
    if (newPassword !== confirmPassword) {
        showAuthMessage('Пароли не совпадают!', 'error');
        return;
    }
    
    // Проверяем длину пароля
    if (newPassword.length < 6) {
        showAuthMessage('Пароль должен содержать минимум 6 символов', 'error');
        return;
    }
    
    const submitBtn = event.target.querySelector('button[type="submit"]');
    const originalText = submitBtn.querySelector('.button-text').textContent;
    submitBtn.querySelector('.button-text').innerHTML = '<span class="auth-loading"></span>';
    submitBtn.disabled = true;
    
    try {
        const response = await fetch(`${AUTH_API_URL}/auth/simple-reset-password`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                email: email,
                new_password: newPassword
            })
        });
        
        if (response.ok) {
            const data = await response.json();
            showAuthMessage(`✅ ${data.message}`, 'success');
            
            // Очищаем форму
            document.getElementById('reset-email').value = '';
            document.getElementById('reset-new-password').value = '';
            document.getElementById('reset-confirm-password').value = '';
            
            // Через 2 секунды переключаем на форму входа
            setTimeout(() => {
                switchAuthTab('login');
                showAuthMessage('Теперь вы можете войти с новым паролем', 'success');
            }, 2000);
        } else {
            const error = await response.json();
            showAuthMessage(error.detail || 'Ошибка сброса пароля. Проверьте email.', 'error');
        }
    } catch (error) {
        console.error('Reset password error:', error);
        showAuthMessage('Ошибка соединения с сервером', 'error');
    } finally {
        submitBtn.querySelector('.button-text').innerHTML = originalText;
        submitBtn.disabled = false;
    }
}

function showAuthMessage(text, type = 'error') {
    if (!authElements.messageDiv) return;
    
    authElements.messageDiv.textContent = text;
    authElements.messageDiv.className = `auth-message ${type}`;
    authElements.messageDiv.style.display = 'block';
    
    setTimeout(() => {
        authElements.messageDiv.style.display = 'none';
    }, 5000);
}

function hideAuthMessage() {
    if (authElements.messageDiv) {
        authElements.messageDiv.style.display = 'none';
    }
}


async function handleLogin(event) {
    event.preventDefault();
    
    const email = document.getElementById('login-email').value;
    const password = document.getElementById('login-password').value;
    
    const submitBtn = event.target.querySelector('button[type="submit"]');
    const originalText = submitBtn.querySelector('.button-text').textContent;
    submitBtn.querySelector('.button-text').innerHTML = '<span class="auth-loading"></span>';
    submitBtn.disabled = true;
    
    try {
        const response = await fetch(`${AUTH_API_URL}/auth/jwt/login`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/x-www-form-urlencoded',
            },
            body: new URLSearchParams({
                username: email,
                password: password,
            }),
            credentials: 'include' 
        });
        
        if (response.ok) {
            showAuthMessage('Вход выполнен успешно!', 'success');
            await checkAuth(); // проверка что Cookie установились
        } else {
            const error = await response.json();
            showAuthMessage(error.detail || 'Ошибка входа. Проверьте email и пароль.', 'error');
        }
    } catch (error) {
        showAuthMessage('Ошибка соединения с сервером', 'error');
    } finally {
        submitBtn.querySelector('.button-text').innerHTML = originalText;
        submitBtn.disabled = false;
    }
}

async function handleRegister(event) {
    event.preventDefault();
    
    const email = document.getElementById('register-email').value;
    const password = document.getElementById('register-password').value;
    
    if (password.length < 6) {
        showAuthMessage('Пароль должен содержать минимум 6 символов', 'error');
        return;
    }
    
    const submitBtn = event.target.querySelector('button[type="submit"]');
    const originalText = submitBtn.querySelector('.button-text').textContent;
    submitBtn.querySelector('.button-text').innerHTML = '<span class="auth-loading"></span>';
    submitBtn.disabled = true;
    
    try {
        const response = await fetch(`${AUTH_API_URL}/auth/register`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                email: email,
                password: password,
            }),
            credentials: 'include' 
        });
        
        if (response.ok) {
            showAuthMessage('Регистрация успешна! Теперь вы можете войти.', 'success');
            switchAuthTab('login');
            document.getElementById('login-email').value = email;
            document.getElementById('register-email').value = '';
            document.getElementById('register-password').value = '';
        } else {
            const error = await response.json();
            showAuthMessage(error.detail || 'Ошибка регистрации. Возможно, email уже используется.', 'error');
        }
    } catch (error) {
        showAuthMessage('Ошибка соединения с сервером', 'error');
    } finally {
        submitBtn.querySelector('.button-text').innerHTML = originalText;
        submitBtn.disabled = false;
    }
}

// Проверка авторизации через Cookie
async function checkAuth() {
    
    try {
        const response = await fetch(`${AUTH_API_URL}/users/me`, {
            credentials: 'include'  // Отправляем Cookie с запросом
        });
        
        if (response.ok) {
             const user = await response.json();
            console.log(`Пользователь ${user.email} уже авторизован, перенаправляем на главную`);
            window.location.href = '/';  // Редирект на главную страницу
        } else {
            // Если пользователь не авторизован, показываем формы
            showAuthForms(true);
        }
    } catch (error) {
        console.error('Auth check error:', error);
        showAuthForms(true);
    }
}


function showAuthForms(show) {
    if (show) {
        if (authElements.tabsContainer) {
            authElements.tabsContainer.classList.remove('hidden');
        }
        authElements.userInfo.classList.add('hidden');
        authElements.loginForm.classList.add('active');
        authElements.registerForm.classList.remove('active');
        
        // назначение активной вкладки
        authElements.tabs.forEach(tab => {
            if (tab.dataset.tab === 'login') {
                tab.classList.add('active');
            } else {
                tab.classList.remove('active');
            }
        });
    }
}

// выход из системы с удалением Cookie на сервере
async function handleLogout() {
    try {
        const response = await fetch(`${AUTH_API_URL}/auth/jwt/logout`, {
            method: 'POST',
            credentials: 'include'  // отправляем Cookie для удаления на сервере
        });
        
   window.location.href = '/auth-page';
    } catch (error) {
        console.error('Logout error:', error);
        window.location.href = '/auth-page';
    }

}

function goToChat() {
    window.location.href = '/';
}

// экспорт функции для использования в HTML
window.handleLogout = handleLogout;
window.goToChat = goToChat;