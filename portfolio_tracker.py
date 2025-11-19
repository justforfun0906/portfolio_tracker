import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.express as px
from datetime import datetime, timedelta

# Set page configuration
st.set_page_config(page_title="Stock Portfolio Tracker", layout="wide")

def main():
    st.title("📈 Stock Portfolio Tracker")
    st.markdown("""
    Add stocks to your portfolio in the sidebar and adjust the time slider to see how your 
    portfolio value would have performed over time.
    """)

    # --- Session State Management ---
    # Initialize portfolio in session state if it doesn't exist
    if 'portfolio' not in st.session_state:
        st.session_state.portfolio = []

    # --- Sidebar: Input & Portfolio Management ---
    with st.sidebar:
        st.header("Manage Portfolio")
        
        # --- NEW: Save & Load Section ---
        with st.expander("💾 Save & Load Portfolio", expanded=True):
            st.caption("Download your data to save it, and upload it when you return.")
            
            # 1. Download Logic
            if st.session_state.portfolio:
                # Convert current portfolio to CSV
                csv_df = pd.DataFrame(st.session_state.portfolio)
                csv_data = csv_df.to_csv(index=False).encode('utf-8')
                
                st.download_button(
                    label="Download Portfolio (CSV)",
                    data=csv_data,
                    file_name="my_portfolio.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            
            # 2. Upload Logic
            uploaded_file = st.file_uploader("Load Portfolio", type=['csv'])
            if uploaded_file is not None:
                try:
                    # Read CSV
                    uploaded_df = pd.read_csv(uploaded_file)
                    
                    # Validate format
                    if 'ticker' in uploaded_df.columns and 'shares' in uploaded_df.columns:
                        # Convert back to list of dicts
                        st.session_state.portfolio = uploaded_df.to_dict('records')
                        st.success("Portfolio loaded successfully!")
                        # No rerun needed here usually, but helps refresh the UI immediately if glitchy
                    else:
                        st.error("CSV must have 'ticker' and 'shares' columns.")
                except Exception as e:
                    st.error(f"Error loading file: {e}")

        # Input form
        with st.form(key='add_stock_form'):
            ticker_input = st.text_input("Stock Ticker (e.g., AAPL, MSFT)", value="").upper()
            shares_input = st.number_input("Number of Shares", min_value=0.01, value=1.0, step=0.1)
            submit_button = st.form_submit_button(label='Add Stock')

        # Add stock logic
        if submit_button:
            if ticker_input:
                # Basic check to see if it's already added
                if any(d['ticker'] == ticker_input for d in st.session_state.portfolio):
                    st.warning(f"{ticker_input} is already in your portfolio.")
                else:
                    # Verify ticker validity by trying to fetch info (lightweight check)
                    try:
                        ticker_data = yf.Ticker(ticker_input)
                        # We fetch history just to check if it exists/is valid
                        hist = ticker_data.history(period="1d")
                        if not hist.empty:
                            st.session_state.portfolio.append({
                                "ticker": ticker_input,
                                "shares": shares_input
                            })
                            st.success(f"Added {ticker_input}")
                        else:
                            st.error(f"Could not find data for {ticker_input}.")
                    except Exception as e:
                        st.error(f"Error adding ticker: {e}")
            else:
                st.warning("Please enter a ticker symbol.")

        # Display Current Portfolio in Sidebar
        st.subheader("Your Assets")
        if st.session_state.portfolio:
            for i, item in enumerate(st.session_state.portfolio):
                col1, col2, col3 = st.columns([2, 2, 1])
                col1.write(f"**{item['ticker']}**")
                col2.write(f"{item['shares']} sh")
                if col3.button("❌", key=f"remove_{i}"):
                    st.session_state.portfolio.pop(i)
                    st.rerun()
        else:
            st.info("No stocks added yet.")

    # --- Main Content Area ---
    
    if not st.session_state.portfolio:
        st.info("👈 Please add stocks using the sidebar or Upload a CSV to generate the chart.")
        return

    # 1. Controls
    col_controls, col_metrics = st.columns([2, 1])
    
    with col_controls:
        st.subheader("Time Interval Settings")
        # Slider for days lookback
        days_lookback = st.slider(
            "History Duration (Days)", 
            min_value=30, 
            max_value=365 * 5, # Up to 5 years
            value=365, 
            step=30
        )

    # 2. Data Fetching & Processing
    with st.spinner('Fetching market data...'):
        try:
            # Prepare list of tickers
            tickers = [item['ticker'] for item in st.session_state.portfolio]
            share_map = {item['ticker']: item['shares'] for item in st.session_state.portfolio}

            # Calculate dates
            # We set end_date to today (exclusive), ensuring we only fetch up to yesterday's close
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days_lookback)
            
            # Download data
            # using threads=True for faster download
            df = yf.download(tickers, start=start_date, end=end_date, progress=False)['Close']

            # Handle case where yfinance returns a Series (single stock) vs DataFrame (multiple)
            if isinstance(df, pd.Series):
                df = df.to_frame(name=tickers[0])

            # Drop rows where all data is NaN (e.g. non-trading days)
            df.dropna(how='all', inplace=True)

            # Calculate Value for each stock: Price * Shares
            portfolio_value_df = pd.DataFrame(index=df.index)
            
            for ticker in tickers:
                if ticker in df.columns:
                    portfolio_value_df[ticker] = df[ticker] * share_map[ticker]
            
            # Calculate Total Portfolio Value
            portfolio_value_df['Total Value'] = portfolio_value_df.sum(axis=1)

            # --- Display Metrics ---
            current_total = portfolio_value_df['Total Value'].iloc[-1]
            start_total = portfolio_value_df['Total Value'].iloc[0]
            delta = current_total - start_total
            delta_percent = (delta / start_total) * 100

            with col_metrics:
                st.metric(
                    label="Current Portfolio Value", 
                    value=f"${current_total:,.2f}", 
                    delta=f"{delta:,.2f} ({delta_percent:.2f}%)"
                )

            # --- Charts ---
            st.subheader("Portfolio Performance")
            
            # Main Area Chart (Total Value)
            fig_total = px.area(
                portfolio_value_df, 
                x=portfolio_value_df.index, 
                y='Total Value',
                title=f"Total Portfolio Value (Past {days_lookback} Days)",
                labels={'x': 'Date', 'Total Value': 'Value (USD)'}
            )
            fig_total.update_layout(hovermode="x unified")
            st.plotly_chart(fig_total, use_container_width=True)

            # Individual Stock Performance (Line Chart)
            st.subheader("Individual Asset Contribution")
            # Drop the 'Total Value' column for this chart
            individual_df = portfolio_value_df.drop(columns=['Total Value'])
            
            fig_breakdown = px.line(
                individual_df, 
                x=individual_df.index, 
                y=individual_df.columns,
                title="Value by Asset Over Time",
                labels={'x': 'Date', 'value': 'Holding Value (USD)', 'variable': 'Ticker'}
            )
            fig_breakdown.update_layout(hovermode="x unified")
            st.plotly_chart(fig_breakdown, use_container_width=True)

            # Composition Pie Chart
            current_composition = individual_df.iloc[-1].reset_index()
            current_composition.columns = ['Ticker', 'Value']
            
            fig_pie = px.pie(
                current_composition, 
                values='Value', 
                names='Ticker', 
                title="Current Allocation",
                hole=0.4
            )
            st.plotly_chart(fig_pie, use_container_width=True)

        except Exception as e:
            st.error(f"An error occurred while processing data: {e}")
            st.info("This may happen if a newly added stock doesn't have data for the selected time range.")

if __name__ == "__main__":
    main()