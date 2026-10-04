import redis
import pickle

def store_user_data(redis_client, user_data):
    """
    Store user data in Redis using both the card number and encoding as keys.
    """
    for idx, card in enumerate(user_data['cards']):
        # Create the Redis key using the card number
        card_key = f"card:{card}"

        # Serialize the encoding
        encoding_key = f"encoding:{pickle.dumps(user_data['encodings'][idx])}"

        # Store the data as a Redis hash using the card number as the key
        redis_client.hset(card_key, mapping={
            'name': user_data['names'][idx],
            'pin': user_data['pins'][idx],
            'encoding': pickle.dumps(user_data['encodings'][idx])  # Serialize encoding
        })

        # Store the card number under the encoding key (to enable encoding-based retrieval)
        redis_client.sadd(encoding_key, card)

def retrieve_user_data_by_card(redis_client, card):
    """
    Retrieve user data from Redis using the card number as the key.
    """
    # Generate the Redis key using the card number
    card_key = f"card:{card}"

    # Fetch the hash data for the given card number
    user_data = redis_client.hgetall(card_key)

    if not user_data:
        return None  # Key does not exist

    # Deserialize the encoding data
    return {
        'card': card,
        'name': user_data[b'name'].decode('utf-8'),
        'pin': user_data[b'pin'].decode('utf-8'),
        'encoding': pickle.loads(user_data[b'encoding'])  # Deserialize encoding
    }

def retrieve_card_by_encoding(redis_client, encoding):
    """
    Retrieve all cards associated with a specific encoding.
    """
    # Serialize the encoding to use as a key
    encoding_key = f"encoding:{pickle.dumps(encoding)}"

    # Fetch the set of card numbers associated with the given encoding
    cards = redis_client.smembers(encoding_key)

    return list(cards)  # Return the list of card numbers

def main():
    # Connect to Redis
    redis_client = redis.StrictRedis(host='localhost', port=6379, decode_responses=False)

    # Example user data
    user_data = {
        'cards': ['1D0023A92ABD', '1D0045F9C123'],
        'names': ['Fernando', 'Maria'],
        'pins': ['5678', '1234'],
        'encodings': [
            [-0.07445453, 0.11549976, -0.04402155, ...],  # Example encoding 1
            [-0.13223423, 0.08934567, -0.09123123, ...]   # Example encoding 2
        ]
    }

    # Store the data in Redis
    store_user_data(redis_client, user_data)

    # Retrieve data by card number
    card_to_retrieve = '1D0045F9C123'
    retrieved_data = retrieve_user_data_by_card(redis_client, card_to_retrieve)
    print("Retrieved Data by Card:")
    print(retrieved_data)

    # Retrieve cards by encoding
    encoding_to_retrieve = [-0.07445453, 0.11549976, -0.04402155, ...]  # Example encoding 1
    cards_with_encoding = retrieve_card_by_encoding(redis_client, encoding_to_retrieve)
    print("\nCards with Encoding:")
    print(cards_with_encoding)

if __name__ == "__main__":
    main()
