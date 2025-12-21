-- docker/mysql/init.sql - Database initialization script

-- This script runs automatically when the MySQL container is first created
-- It creates the database, user, and imports the schema

-- Set character set and collation
SET NAMES utf8mb4;
SET CHARACTER SET utf8mb4;

-- Create database if not exists (already done by MYSQL_DATABASE env var, but keeping for safety)
CREATE DATABASE IF NOT EXISTS stockjarvis CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- Grant privileges to the application user
GRANT ALL PRIVILEGES ON stockjarvis.* TO '${MYSQL_USER}'@'%';
FLUSH PRIVILEGES;

-- Use the database
USE stockjarvis;

-- The schema.sql file will be executed after this file
-- due to alphabetical ordering in /docker-entrypoint-initdb.d/

-- Insert default symbols for quick start (Nifty 50 top stocks)
INSERT INTO symbols (symbol, company_name, exchange, is_nifty50, is_fno, is_active, sector, industry) VALUES
('RELIANCE', 'Reliance Industries Ltd', 'NSE', TRUE, TRUE, TRUE, 'Energy', 'Oil & Gas'),
('TCS', 'Tata Consultancy Services Ltd', 'NSE', TRUE, TRUE, TRUE, 'Technology', 'IT Services'),
('HDFCBANK', 'HDFC Bank Ltd', 'NSE', TRUE, TRUE, TRUE, 'Finance', 'Banking'),
('INFY', 'Infosys Ltd', 'NSE', TRUE, TRUE, TRUE, 'Technology', 'IT Services'),
('ICICIBANK', 'ICICI Bank Ltd', 'NSE', TRUE, TRUE, TRUE, 'Finance', 'Banking'),
('HINDUNILVR', 'Hindustan Unilever Ltd', 'NSE', TRUE, TRUE, TRUE, 'Consumer', 'FMCG'),
('SBIN', 'State Bank of India', 'NSE', TRUE, TRUE, TRUE, 'Finance', 'Banking'),
('BHARTIARTL', 'Bharti Airtel Ltd', 'NSE', TRUE, TRUE, TRUE, 'Telecom', 'Telecommunications'),
('ITC', 'ITC Ltd', 'NSE', TRUE, TRUE, TRUE, 'Consumer', 'Diversified'),
('KOTAKBANK', 'Kotak Mahindra Bank Ltd', 'NSE', TRUE, TRUE, TRUE, 'Finance', 'Banking'),
('LT', 'Larsen & Toubro Ltd', 'NSE', TRUE, TRUE, TRUE, 'Industrial', 'Engineering'),
('AXISBANK', 'Axis Bank Ltd', 'NSE', TRUE, TRUE, TRUE, 'Finance', 'Banking'),
('WIPRO', 'Wipro Ltd', 'NSE', TRUE, TRUE, TRUE, 'Technology', 'IT Services'),
('TATAMOTORS', 'Tata Motors Ltd', 'NSE', TRUE, TRUE, TRUE, 'Automotive', 'Automobiles'),
('ASIANPAINT', 'Asian Paints Ltd', 'NSE', TRUE, TRUE, TRUE, 'Consumer', 'Paints'),
('MARUTI', 'Maruti Suzuki India Ltd', 'NSE', TRUE, TRUE, TRUE, 'Automotive', 'Automobiles'),
('HCLTECH', 'HCL Technologies Ltd', 'NSE', TRUE, TRUE, TRUE, 'Technology', 'IT Services'),
('SUNPHARMA', 'Sun Pharmaceutical Industries Ltd', 'NSE', TRUE, TRUE, TRUE, 'Healthcare', 'Pharmaceuticals'),
('BAJFINANCE', 'Bajaj Finance Ltd', 'NSE', TRUE, TRUE, TRUE, 'Finance', 'NBFC'),
('ULTRACEMCO', 'UltraTech Cement Ltd', 'NSE', TRUE, TRUE, TRUE, 'Industrial', 'Cement')
ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP;

-- Insert default strategies
INSERT INTO strategies (name, description, parameters, is_active, is_validated) VALUES
('RSI_Oversold', 'Buy when RSI crosses above 30 (oversold)', '{"rsi_period": 14, "oversold_level": 30}', TRUE, FALSE),
('Golden_Cross', 'Buy when 50-day MA crosses above 200-day MA', '{"short_ma": 50, "long_ma": 200}', TRUE, FALSE),
('Bollinger_Bounce', 'Buy at lower Bollinger Band, sell at upper', '{"period": 20, "std_dev": 2}', TRUE, FALSE),
('MACD_Crossover', 'Trade on MACD signal line crossovers', '{"fast": 12, "slow": 26, "signal": 9}', TRUE, FALSE),
('Volume_Breakout', 'Trade on volume spikes with price breakouts', '{"volume_threshold": 1.5, "breakout_period": 20}', TRUE, FALSE)
ON DUPLICATE KEY UPDATE updated_at = CURRENT_TIMESTAMP;

-- Create indexes for performance optimization (if not already in schema.sql)
-- These are additional indexes for common query patterns

-- Composite index for price queries by symbol and date range
CREATE INDEX IF NOT EXISTS idx_prices_symbol_timestamp_timeframe 
    ON prices(symbol_id, timestamp DESC, timeframe);

-- Index for recent signals queries
CREATE INDEX IF NOT EXISTS idx_signals_created_desc 
    ON signals(created_at DESC);

-- Index for open positions queries
CREATE INDEX IF NOT EXISTS idx_positions_open_updated 
    ON positions(is_open, updated_at DESC);

-- Index for pending orders
CREATE INDEX IF NOT EXISTS idx_orders_pending 
    ON orders(status, created_at DESC);

-- Optimize tables
OPTIMIZE TABLE symbols;
OPTIMIZE TABLE prices;
OPTIMIZE TABLE strategies;
OPTIMIZE TABLE signals;
OPTIMIZE TABLE orders;
OPTIMIZE TABLE positions;

-- Display initialization complete message
SELECT 'StockJarvis database initialized successfully!' AS message;
SELECT COUNT(*) AS symbol_count FROM symbols;
SELECT COUNT(*) AS strategy_count FROM strategies;
