# Import necessary modules and libraries
import aioconsole
import random
import os
from ud3tn_utils.aap2.aap2_client import AAP2AsyncUnixClient
from ud3tn_utils.aap2.generated import aap2_pb2
from aiocoap.message import Message
from aiocoap.numbers.codes import Code
from aiocoap.numbers.types import Type
from aiocoap import Context
import asyncio

# Address of the UD3TN node's AAP2 Unix domain socket
SERVER_ADDRESS = 'ud3tn-a.aap2.socket' 

# Instantiate separate AAP2 clients for sending and receiving
send_client = AAP2AsyncUnixClient(SERVER_ADDRESS)
receive_client = AAP2AsyncUnixClient(SERVER_ADDRESS)

# CoAP Message ID tracking 
MAX_ID = 65535  # Maximum message ID value
MIN_ID = 1      # Minimum message ID value
current_id = 1  # Starting message ID

# Main function that configures clients and runs send/receive tasks concurrently
async def main(send_client, receive_client):
    async with send_client, receive_client:
        # Configure each AAP2 client with an agent ID
        await send_client.configure(agent_id='snd')
        await receive_client.configure(agent_id='rec', subscribe=True)

        # Run sender and receiver tasks concurrently
        await asyncio.gather(
            chat_send(send_client),
            chat_receive(receive_client)
        )

# Asynchronous function to send CoAP messages via the AAP2 client
async def chat_send(send_client):
    try:
        protocol = await Context.create_client_context() # Create CoAP context
        while True:
            message = await aioconsole.ainput("Message or 'exit' to escape: ")
            if message.lower() == "exit":
                break
            else:
                # Construct CoAP message based on input
                if message.lower() == "get":
                    payload = Message(
                        code=Code.GET,
                        uri="coap://localhost/temperature",
                        mtype=Type.NON,
                        mid=current_id
                    )
                elif message.lower() == "get all":
                    payload = Message(
                        code=Code.GET,
                        uri="coap://localhost/temperature?all",
                        mtype=Type.NON,
                        mid=current_id
                    )
                    payload.opt.uri_query = ["all"]
                else:
                    # Send a random temperature reading using PUT
                    temperature = str(round(random.uniform(10, 30), 2))
                    payload = Message(
                        code=Code.PUT,
                        uri="coap://localhost/temperature",
                        mtype=Type.NON,
                        mid=current_id,
                        payload=temperature.encode("utf-8")
                    )
                
                # Set a random 2-byte token for matching responses
                payload.token = os.urandom(2)
                
                # Move to next message ID (wrap around if needed)
                next_mid()
                
                # Encode CoAP message into bytes
                p = payload.encode()

                # Send it wrapped in a Bundle ADU to the destination EID
                await send_client.send_adu(
                    aap2_pb2.BundleADU(
                        dst_eid="dtn://b.dtn/rec",
                        payload_length=len(p),
                    ),
                    p,
                )
                
                print("CoAP Message:", payload)
                print("Encoded:", p)
                
                # Wait for a response from ud3tn agent
                response = await send_client.receive_response()
                print("Response:", response)
    finally:
        await send_client.disconnect()

# Asynchronous function to receive ADUs from the Bundle Protocol, decode the payload as CoAP
async def chat_receive(receive_client):
    try:
        while True:
            # Wait for an incoming ADU 
            adu_msg, recv_payload = await receive_client.receive_adu()
            print(f"Received ADU from {adu_msg.src_eid}: {recv_payload}")

            # Decode the payload as a CoAP message
            response = Message.decode(recv_payload)
            
            status_code = response.code
            mid = response.mid
            token = response.token
            
            print(f"Received Response:")
            print(f"  Status Code: {status_code}")
            print(f"  Message ID (MID): {mid}")
            print(f"  Token: {token.hex() if token else 'None'}")
            print(f"  Payload: {response.payload}")
            
            # Acknowledge successful receipt of the ADU to ud3tn
            await receive_client.send_response_status(aap2_pb2.ResponseStatus.RESPONSE_STATUS_SUCCESS)
    finally:
        await receive_client.disconnect()

# Helper to move to the next message ID, wrapping around after MAX_ID
def next_mid():
    global current_id
    current_id = (current_id % MAX_ID) + 1

# Run the async main function
asyncio.run(main(send_client, receive_client))