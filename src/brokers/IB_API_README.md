# Interactive Brokers API Integration

This document provides a detailed guide for integrating with Interactive Brokers (IB) API services for retrieving transaction data, positions, and account summaries.

## Table of Contents

1. [Overview](#overview)
2. [API Options](#api-options)
3. [Authentication Methods](#authentication-methods)
4. [Usage Examples](#usage-examples)
5. [Troubleshooting](#troubleshooting)
6. [FAQ](#faq)

## Overview

Our system integrates with Interactive Brokers using several API options, providing a robust and fault-tolerant approach to retrieving financial data. The implementation follows a cascading approach, attempting multiple APIs in sequence based on availability and authentication status.

### Key Files

- `src/brokers/ib.py` - Basic account data retrieval (positions, summaries)
- `src/brokers/ib_transactions.py` - Transaction history retrieval
- `setup_ib_flex_credentials.py` - Utility for setting up Flex Query credentials

## API Options

### 1. Client Portal API

- **Endpoint Base**: `https://localhost:5050/v1/api/`
- **Authentication**: Browser-based login through Client Portal Gateway
- **Key Endpoints**:
  - Portfolio data: `/portfolio/{accountId}/positions`
  - Account summary: `/portfolio/{accountId}/summary`
  - Ledger data: `/portfolio/{accountId}/ledger`
  - Allocation data: `/portfolio/{accountId}/allocation`

The Client Portal API requires the IB Client Portal Gateway to be running locally. This interface is suitable for basic account data retrieval.

### 2. Account Management Web API

- **Endpoint Base**: `https://api.ibkr.com/gw/api/v1/`
- **Authentication**: OAuth 2.0
- **Key Endpoints**:
  - Instructions/Transactions: `/instructions/query`

The Account Management Web API provides comprehensive transaction history but requires proper OAuth 2.0 authentication setup. This is the recommended approach for production environments needing detailed transaction data.

### 3. Flex Query API

- **Endpoint Base**: 
  - Request: `https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.SendRequest`
  - Retrieve: `https://gdcdyn.interactivebrokers.com/Universal/servlet/FlexStatementService.GetStatement`
- **Authentication**: Flex Query ID and Token
- **Data Format**: XML

The Flex Query API provides the most comprehensive and detailed transaction data in XML format. It's ideal for historical data analysis and reconciliation processes.

## Authentication Methods

### Client Portal Gateway Authentication

The Client Portal Gateway provides a lightweight authentication method:

1. Start the Gateway: `cd path/to/clientportal.gw && bin/run.sh root/conf.yaml`
2. Complete browser-based authentication when prompted
3. The session will remain authenticated for API calls

### OAuth 2.0 Authentication

For the Account Management Web API, OAuth 2.0 authentication is required:

1. Register your application with Interactive Brokers:
   - Go to https://www.interactivebrokers.com/
   - Navigate to Settings > API Settings > OAuth
   - Register a new application and obtain client_id and client_secret

2. Implement OAuth 2.0 flow:
   - Authorization Code Flow for server-side applications
   - Use the authorization URL: `https://api.ibkr.com/v1/oauth/authorize`
   - Get tokens from: `https://api.ibkr.com/v1/oauth/token`
   - Include necessary scopes for transaction data access

3. Use the access token in your API requests:
   ```python
   headers = {
       "Content-Type": "application/json",
       "Authorization": f"Bearer {access_token}"
   }
   ```

For more information, refer to the [IBKR Web API documentation](https://www.interactivebrokers.com/campus/ibkr-api-page/web-api-account-management/).

### Flex Query Authentication

The Flex Query API uses a token-based authentication:

1. Generate a Flex Query ID:
   - Log into the IBKR Account Management
   - Go to Reports > Flex Queries
   - Create a new Flex Query with desired specifications

2. Generate a Flex Web Service token:
   - In Account Management, go to Reports > Settings > Flex Web Service
   - Create a new token

3. Use the `setup_ib_flex_credentials.py` utility to store these credentials

## Usage Examples

### Basic Position Data Retrieval

```python
from src.brokers.ib import IBDataSource

# Initialize the data source
ib_source = IBDataSource(account_id="YOUR_ACCOUNT_ID")

# Get positions
positions = ib_source.get_positions()
print(f"Found {len(positions)} positions")
```

### Transaction History Retrieval

```python
from src.brokers.ib_transactions import IBTransactionDataSource
import datetime

# Initialize with standard Client Portal API access
transaction_source = IBTransactionDataSource(account_id="YOUR_ACCOUNT_ID")

# Initialize with Flex Query credentials
flex_transaction_source = IBTransactionDataSource(
    account_id="YOUR_ACCOUNT_ID",
    flex_query_id="YOUR_FLEX_QUERY_ID",
    token="YOUR_FLEX_TOKEN"
)

# Initialize with OAuth for Account Management Web API
oauth_transaction_source = IBTransactionDataSource.from_oauth_credentials(
    client_id="YOUR_CLIENT_ID",
    client_secret="YOUR_CLIENT_SECRET",
    account_id="YOUR_ACCOUNT_ID"
)

# Define date range
start_date = datetime.date(2023, 1, 1)
end_date = datetime.date(2023, 3, 31)

# Get transactions
transactions = transaction_source.get_transactions(start_date, end_date)
print(f"Found {len(transactions)} transactions")
```

## Troubleshooting

### Common Issues

1. **Authentication Errors**:
   - For Client Portal API: Ensure the Gateway is running and you've completed browser authentication
   - For OAuth: Check token validity and refresh if expired
   - For Flex Query: Verify token and query ID are correct

2. **"404 Not Found" Errors**:
   - Some endpoints may not be available for your account type
   - Our implementation gracefully handles this by trying alternative endpoints

3. **No Transactions Found**:
   - Check date range is correct
   - Verify that account has transactions in the specified period
   - Try using Flex Query API for historical transactions

### Gateway Issues

If the Client Portal Gateway isn't connecting:

1. Check if it's running: `ps aux | grep clientportal`
2. Restart the Gateway if needed
3. Check logs in the Gateway directory
4. Ensure proper network connectivity to localhost:5050

## FAQ

### Which API should I use?

- **For basic account data**: Client Portal API is simplest
- **For comprehensive transaction history**: Use Flex Query API or Account Management Web API
- **For production environments**: Implement OAuth 2.0 with Account Management Web API

### How secure are my credentials?

- OAuth tokens should be stored securely and refreshed regularly
- Flex Query tokens have limited access to specific reports only
- Consider using environment variables or a secure credential store

### Can I get real-time data?

- These APIs primarily provide snapshot/historical data
- For real-time data, consider IB's WebSocket API or Trader Workstation API

### Do I need to maintain multiple authentication methods?

- We recommend implementing at least two methods for redundancy
- Our implementation automatically tries multiple endpoints if one fails

---

For additional information, please refer to:
- [Interactive Brokers API Documentation](https://www.interactivebrokers.com/en/index.php?f=5039)
- [Client Portal API Guide](https://www.interactivebrokers.com/campus/ibkr-api-page/client-portal-api/)
- [Account Management Web API](https://www.interactivebrokers.com/campus/ibkr-api-page/web-api-account-management/) 