from fastapi import FastAPI

from app.errors import install_error_handlers
from app.routers import auth, balances, categories, currencies, expenses, friends, groups, health, users

app = FastAPI(title="SplitApp API", version="0.1.1")
install_error_handlers(app)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(currencies.router)
app.include_router(users.router)
app.include_router(categories.router)
app.include_router(friends.router)
app.include_router(groups.router)
app.include_router(balances.router)
app.include_router(expenses.router)
