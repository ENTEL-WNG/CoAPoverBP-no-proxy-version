# Import necessary modules and libraries
import aioconsole
import random
import os
from ud3tn_utils.aap2.aap2_client import AAP2AsyncUnixClient
from ud3tn_utils.aap2.generated import aap2_pb2
import sys
import os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'aiocoap', 'src'))
sys.path.insert(0, project_root)
from aiocoap.message import Message
from aiocoap.numbers.codes import Code
from aiocoap.numbers.types import Type
import asyncio

# Address of the UD3TN node's AAP2 Unix domain socket
CLIENT_ADDRESS = 'ud3tn-a.aap2.socket' 

# Instantiate separate AAP2 clients for sending and receiving
send_client = AAP2AsyncUnixClient(CLIENT_ADDRESS)
receive_client = AAP2AsyncUnixClient(CLIENT_ADDRESS)

# CoAP Message ID tracking 
MAX_ID = 16777215  # Maximum message ID value
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
    BUFFER_LIMIT = 5
    TIMEOUT_SECONDS = 10

    coap_buffer = []
    flusher_task = None

    async def flush_buffer():
        nonlocal coap_buffer, flusher_task
        if not coap_buffer:
            return
        aggregate_payload = b''.join(coap_buffer)
        await send_client.send_adu(
            aap2_pb2.BundleADU(
                dst_eid="dtn://b.dtn/rec",
                payload_length=len(aggregate_payload),
            ),
            aggregate_payload,
        )
        print(f"Sent aggregated bundle with {len(coap_buffer)} CoAP messages")
        coap_buffer.clear()
        if flusher_task:
            flusher_task.cancel()
            flusher_task = None

    async def start_flusher():
        await asyncio.sleep(TIMEOUT_SECONDS)
        await flush_buffer()

    try:

        while True:
            message = await aioconsole.ainput("Message or 'exit' to escape: ")

            if message.lower() == "exit":
                await flush_buffer()
                break
            else:
                # Build CoAP message
                temperature = str(round(random.uniform(10, 30), 2))
                payload = Message(
                    code=Code.PUT,
                    uri="coap://localhost/temperature",
                    mtype=Type.NON,
                    mid=current_id,
                    payload=temperature.encode("utf-8")
                )
                payload.opt.payload_length = len(payload.payload)
                payload.token = os.urandom(2)
                next_mid()

                p = payload.encode()

                # Add to buffer
                coap_buffer.append(p)
                print(f"Queued CoAP Message MID={payload.mid}, Token={payload.token.hex()}")

                # Start flusher if needed
                if not flusher_task:
                    flusher_task = asyncio.create_task(start_flusher())

                # Flush immediately if buffer limit reached
                if len(coap_buffer) >= BUFFER_LIMIT:
                    await flush_buffer()

    finally:
        if flusher_task:
            flusher_task.cancel()
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
            
            print(f"Received Response:")
            print(f"  Status Code: {response.code}")
            print(f"  Message ID (MID): {response.mid}")
            print(f"  Token: {response.token.hex() if response.token else 'None'}")
            print(f"  Payload: {response.payload}")
            print(f"  Mtype: {response.mtype}")
            
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