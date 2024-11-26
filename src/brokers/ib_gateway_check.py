from ib_insync import *
import logging
import time
import socket


def check_port_status():
    """Check if port 4001 is open"""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(("127.0.0.1", 4001))
    sock.close()
    return result == 0


def test_connection():
    print("\nTesting connection to IB Gateway...")
    ib = IB()

    # First check if port is open
    if not check_port_status():
        print("Port 4001 is not open. Please check:")
        print("1. IB Gateway is running")
        print("2. API settings are configured for port 4001")
        print("3. You're logged into your account")
        return False

    try:
        # Connect to port 4001
        ib.connect(host="127.0.0.1", port=4001, clientId=1, timeout=15)  # Updated port

        # Wait a bit to ensure connection is established
        time.sleep(2)

        if ib.isConnected():
            print("\nSuccessfully connected to IB Gateway!")
            print(f"Client ID: {ib.client.clientId}")
            print(f"Server Version: {ib.client.serverVersion}")

            # Test basic API functionality
            accounts = ib.managedAccounts()
            print(f"\nAccounts available: {accounts}")

            return True

    except ConnectionRefusedError:
        print("\nConnection refused. Please verify:")
        print("1. IB Gateway is running and logged in")
        print("2. API settings are configured for port 4001")
        print("3. You're not in paper trading mode (unless intended)")
    except Exception as e:
        print(f"\nUnexpected error: {str(e)}")
    finally:
        if ib.isConnected():
            ib.disconnect()
            print("\nDisconnected from IB Gateway")

    return False


if __name__ == "__main__":
    util.logToConsole(logging.DEBUG)
    test_connection()
