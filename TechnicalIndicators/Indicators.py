import pandas as pd


## Simple Moving Average
def SMA(df, n, column):
    ## D:\projects\Fin-start1\Indicators.py:7: FutureWarning: pd.rolling_mean is deprecated for Series and will be removed in a future version, replace with
    ## Series.rolling(window=10,center=False).mean()
    ## MA = pd.Series(pd.rolling_mean(df['ClosePrice'], n), name='MA_' + str(n))
    MA = pd.Series(pd.rolling_mean(df[column], n), name='MA_' + str(n))

    # MA = pd.Series(pd.Series.rolling(window=n, on=df[column]).mean(), name='MA_' + str(n))

    df = df.join(MA)
    return df


## Exponential Moving Average
def EMA(df, n, column):
    EMA = pd.Series(pd.ewma(df[column], span=n, min_periods=n - 1), name='EMA_' + str(n))
    df = df.join(EMA)
    return df


# Bollinger Bands
def BBANDS(df, n):
    MA = pd.Series(pd.rolling_mean(df['Close'], n))
    MSD = pd.Series(pd.rolling_std(df['Close'], n))
    b1 = 4 * MSD / MA
    B1 = pd.Series(b1, name='BollingerB_' + str(n))
    df = df.join(B1)
    b2 = (df['Close'] - MA + 2 * MSD) / (4 * MSD)
    B2 = pd.Series(b2, name='Bollinger%b_' + str(n))
    df = df.join(B2)
    return df


## Upper Bollinger Band

## Lower Bollinger Band

## RSI
def RSI():
    print(RSI)


# Pivot Points, Supports and Resistances
def PPSR(df):
    PP = pd.Series((df['High'] + df['Low'] + df['Close']) / 3)
    R1 = pd.Series(2 * PP - df['Low'])
    S1 = pd.Series(2 * PP - df['High'])
    R2 = pd.Series(PP + df['High'] - df['Low'])
    S2 = pd.Series(PP - df['High'] + df['Low'])
    R3 = pd.Series(df['High'] + 2 * (PP - df['Low']))
    S3 = pd.Series(df['Low'] - 2 * (df['High'] - PP))
    psr = {'PP': PP, 'R1': R1, 'S1': S1, 'R2': R2, 'S2': S2, 'R3': R3, 'S3': S3}
    PSR = pd.DataFrame(psr)
    df = df.join(PSR)
    return df

## Candlestick patterns Identification


##  Historic Support and Resistances

##  Pivot Points


##  Fibonacci Retracement


## The Moving Average Convergence Divergence (MACD) Indicator


## Stochastics


##  TRIX

##  Time Series Forecast


##  Trade Volume Index


##  Trade Intensity Index


## True Range

##  Twiggs Money Flow


##  Typical Price


##  Ulcer Index


##  Ultimatee Oscillator


##  VWAP


##  Valuation Lines


##  Vertical Horizontal Filter


##  Volume Chart


##  Volume OScillator


##  Volume Profile


##  Volume Rate of Change


##  Volume Underlay


##  Vortex Indicator


##  Weighted Close


##  Williams %R


##  Pring's Know Sure Thing


##  Pring's Special K


##  Psycological Line


##  QStick


##  RAVI


##  Rainbow Moving Average


##  Rainbow Oscillator


##  Random Walk Index


##  Relative Vigor Index


##  Relative Volatility


##  STARC Bands


##  Schaff  Trend cycle


##  Shinohara  Intensity Ratio


##  Standard DEviation


##  Stochastic Momentum Index


##  Supertrend


## Swing Index


##  Lowest Low Value


##  Market Facilitation Index


##  Mass Index


##   Median  Price


##  Momentum Indicator


##  Money Flow Index


##  Moving Average Deviation


##  Moving average Envelope


##  NEgative Volume Index


##  On Balance Volume


##  Parabolic SAR


##  Positive Volume Index


##  Pretty Good Oscilator


##  Price Momentum Oscillator


##  Price OScillator


##  Price Rate of Change


##  Price Volume Trend


##  Prime Number bands


##  Elder Force Index


##  Elder Impulse system


##  Elder Ray Index


##  Fractual Chaos Bands


##  Factual Chaos Oscillator


##  Gattor Oscillator


##  Gopalkrishnan Range Index


##  High Low Bands


##  High Minus Low


##  Highest High Value


##  Historical Volatility


##  Ichimoku Clouds


##  Intraday Momentum Index


##  Keltner Channel


##  Kinger Volume Oscillator


##  Linear Reg Forecast


## Linear Reg Intercept


##  Linear Reg R2


##  Linear Reg slope


##  Bollinger %b


##  Bollinger bandwidth


##  Center of gravity


##  Chaikin Money Flow


##  Chjaikin Volatility


##  Chande Forecast Oscillator


##  Chande Momentum Oscillator


##  Choppiness Index


##  Commodity Channel Index


##  Coppock Curve


##  Correlation coefficient


##  Darvas  Box


##  detrebded  price oscillator


##  Disparity Index


##  Donchian Channel


##  Ease of Momentum


##  Ehler Fisher Transform


##  ADX/DMS


##  ATR Bands


##  ATR trailing Stops


##  Accumulation/Distribution


##  Accumulative Swing Index


##  Alligator


## Aroon

##  Aroon Oscillator


## Average True Range


##  Awesome Oscillator


##  Balance of Power
