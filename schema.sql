-- StockJarvis Database Schema
-- Normalized schema replacing per-stock tables

-- Create database
CREATE DATABASE IF NOT EXISTS stockjarvis CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE stockjarvis;

-- Symbols table
CREATE TABLE symbols (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol VARCHAR(20) NOT NULL UNIQUE,
    company_name VARCHAR(255) NOT NULL,
    exchange ENUM('NSE', 'BSE') NOT NULL DEFAULT 'NSE',
    is_nifty50 BOOLEAN DEFAULT FALSE,
    is_fno BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    sector VARCHAR(100),
    industry VARCHAR(100),
    isin VARCHAR(20),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_symbol (symbol),
    INDEX idx_active (is_active)
) ENGINE=InnoDB;

-- Prices table (unified OHLCV data)
CREATE TABLE prices (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    symbol_id INT NOT NULL,
    timestamp DATETIME NOT NULL,
    open FLOAT NOT NULL,
    high FLOAT NOT NULL,
    low FLOAT NOT NULL,
    close FLOAT NOT NULL,
    volume FLOAT NOT NULL,
    timeframe ENUM('1min', '5min', '15min', '1hour', 'daily', 'weekly', 'monthly') NOT NULL DEFAULT 'daily',
    turnover FLOAT,
    FOREIGN KEY (symbol_id) REFERENCES symbols(id) ON DELETE CASCADE,
    UNIQUE KEY uix_symbol_time_tf (symbol_id, timestamp, timeframe),
    INDEX idx_symbol_timeframe (symbol_id, timeframe),
    INDEX idx_timestamp (timestamp)
) ENGINE=InnoDB;

-- Strategies table
CREATE TABLE strategies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    parameters TEXT,
    backtest_accuracy FLOAT,
    backtest_sharpe FLOAT,
    backtest_max_drawdown FLOAT,
    is_active BOOLEAN DEFAULT TRUE,
    is_validated BOOLEAN DEFAULT FALSE,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_active (is_active)
) ENGINE=InnoDB;

-- Signals table
CREATE TABLE signals (
    id INT AUTO_INCREMENT PRIMARY KEY,
    strategy_id INT NOT NULL,
    symbol_id INT NOT NULL,
    action ENUM('BUY', 'SELL') NOT NULL,
    price FLOAT NOT NULL,
    stop_loss FLOAT NOT NULL,
    target FLOAT NOT NULL,
    confidence FLOAT,
    reason TEXT,
    is_executed BOOLEAN DEFAULT FALSE,
    executed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE CASCADE,
    FOREIGN KEY (symbol_id) REFERENCES symbols(id) ON DELETE CASCADE,
    INDEX idx_symbol_created (symbol_id, created_at),
    INDEX idx_strategy_created (strategy_id, created_at),
    INDEX idx_executed (is_executed)
) ENGINE=InnoDB;

-- Orders table
CREATE TABLE orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    signal_id INT,
    symbol_id INT NOT NULL,
    action ENUM('BUY', 'SELL') NOT NULL,
    quantity INT NOT NULL,
    price FLOAT NOT NULL,
    broker_order_id VARCHAR(100) UNIQUE,
    status ENUM('PENDING', 'PLACED', 'COMPLETED', 'CANCELLED', 'REJECTED') NOT NULL DEFAULT 'PENDING',
    filled_quantity INT DEFAULT 0,
    average_price FLOAT,
    trading_mode ENUM('paper', 'live') NOT NULL DEFAULT 'paper',
    error_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    executed_at DATETIME,
    FOREIGN KEY (signal_id) REFERENCES signals(id),
    FOREIGN KEY (symbol_id) REFERENCES symbols(id) ON DELETE CASCADE,
    INDEX idx_status_created (status, created_at),
    INDEX idx_broker_order (broker_order_id)
) ENGINE=InnoDB;

-- Positions table
CREATE TABLE positions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    symbol_id INT NOT NULL,
    quantity INT NOT NULL,
    entry_price FLOAT NOT NULL,
    current_price FLOAT NOT NULL,
    stop_loss FLOAT,
    target FLOAT,
    realized_pnl FLOAT DEFAULT 0.0,
    unrealized_pnl FLOAT DEFAULT 0.0,
    is_open BOOLEAN DEFAULT TRUE,
    trading_mode ENUM('paper', 'live') NOT NULL DEFAULT 'paper',
    entry_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    exit_time DATETIME,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (symbol_id) REFERENCES symbols(id) ON DELETE CASCADE,
    INDEX idx_symbol_open (symbol_id, is_open),
    INDEX idx_open (is_open)
) ENGINE=InnoDB;

-- Backtest results table
CREATE TABLE backtest_results (
    id INT AUTO_INCREMENT PRIMARY KEY,
    strategy_id INT NOT NULL,
    start_date DATE NOT NULL,
    end_date DATE NOT NULL,
    initial_capital FLOAT NOT NULL,
    final_capital FLOAT NOT NULL,
    total_trades INT NOT NULL,
    winning_trades INT NOT NULL,
    losing_trades INT NOT NULL,
    accuracy FLOAT NOT NULL,
    sharpe_ratio FLOAT,
    sortino_ratio FLOAT,
    max_drawdown FLOAT,
    max_drawdown_duration INT,
    total_return FLOAT,
    annual_return FLOAT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (strategy_id) REFERENCES strategies(id) ON DELETE CASCADE,
    INDEX idx_strategy_created (strategy_id, created_at)
) ENGINE=InnoDB;

-- Alerts table
CREATE TABLE alerts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(255) NOT NULL,
    message TEXT NOT NULL,
    email_sent BOOLEAN DEFAULT FALSE,
    sms_sent BOOLEAN DEFAULT FALSE,
    metadata TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_type_created (type, created_at),
    INDEX idx_created (created_at)
) ENGINE=InnoDB;
