# Pharmaceutical Inventory Management System

This is a **Flask-based Pharmaceutical Inventory Management System** designed to efficiently manage stock, procurement, and distribution. The system offers user authentication, product inventory management, and transaction tracking.

## Features
- **User Authentication**: Secure login using Flask-Login.
- **Inventory Management**: Add, update, and delete products.
- **Stock Management**: Track stock-in and stock-out operations.
- **Transaction Management**: Monitor purchase and sales transactions.
- **Dashboard**: Visual overview of product statistics.

## Prerequisites
Ensure you have the following installed:
- Python 3.8 or higher
- Flask
- SQLAlchemy
- Flask-Login

## Installation
1. Clone the repository:
    ```bash
    git clone  https://github.com/UserSky21/Pharmaceutical-Inventory-System-.git
    cd pharmaceutical-Inventory-System
    ```

2. Create and activate a virtual environment:
    ```bash
    python -m venv env
    source env/bin/activate  # On Linux/Mac
    env\Scripts\activate  # On Windows
    ```

3. Install dependencies:
    ```bash
    pip install -r requirements.txt
    ```

4. Set up environment variables by creating a `.env` file:
    ```
    SECRET_KEY=your_secret_key
    DATABASE_URL=sqlite:///inventory.db
    ```

5. Initialize the database:
    ```bash
    python app.py db init
    python app.py db migrate
    python app.py db upgrade
    ```

## Usage
1. Run the application:
    ```bash
    python app.py
    ```
2. Access the web interface at:
    ```
    http://127.0.0.1:5000/
    ```
3. Log in or create an account.
   Username : admin
   Password : admin123
5. Navigate through the dashboard to manage inventory, monitor stock, and track transactions.

## Project Structure
```
pharmaceutical-inventory-management/
├── app.py
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── index.html
│   ├── login.html
│   ├── products.html
│   ├── stock_in.html
│   ├── transactions.html
├── .gitignore
├── requirements.txt
```

## Contributing
Contributions are welcome! Feel free to fork the repo and submit a pull request.
