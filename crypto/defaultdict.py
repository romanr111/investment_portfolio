from collections import defaultdict

def_dict = defaultdict(int)  # Pass list to .default_factory
def_dict['BTC'] += 1  # Access a missing key returns an empty list

print(def_dict)
print(def_dict['BTC'])