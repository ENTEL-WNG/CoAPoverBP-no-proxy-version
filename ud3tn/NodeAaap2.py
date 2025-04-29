# Imports
import asyncio
import aioconsole
import random
import os
import sys

from ud3tn_utils.aap2.aap2_client import AAP2AsyncUnixClient
from ud3tn_utils.aap2.generated import aap2_pb2

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'aiocoap', 'src'))
sys.path.insert(0, project_root)
import aiocoap
from aiocoap.message import Message
from aiocoap.numbers.codes import Code
from aiocoap.numbers.types import Type

# ----------------------------
# Configuration
# ----------------------------

CLIENT_ADDRESS = 'ud3tn-a.aap2.socket'
MAX_ID = 16777215
current_id = 1

# Instantiate clients
send_client = AAP2AsyncUnixClient(CLIENT_ADDRESS)
receive_client = AAP2AsyncUnixClient(CLIENT_ADDRESS)

# ----------------------------
# Helper Functions
# ----------------------------

def next_mid():
    global current_id
    current_id = (current_id % MAX_ID) + 1

# ----------------------------
# Main Async Functions
# ----------------------------

async def main(send_client, receive_client):
    async with send_client, receive_client:
        await send_client.configure(agent_id='snd')
        await receive_client.configure(agent_id='rec', subscribe=True)

        await asyncio.gather(
            chat_send(send_client),
            chat_receive(receive_client)
        )

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
            print("Commands: post, put, get, delete, exit")
            command = await aioconsole.ainput("Enter command: ")

            if command.lower() == "exit":
                await flush_buffer()
                break

            elif command.lower() == "post":
                resource_name = await aioconsole.ainput("Enter new resource name: ")

                payload = Message(
                    code=Code.POST,
                    uri="coap://b.dtn.arpa/",
                    mtype=Type.NON,
                    mid=current_id,
                    payload=resource_name.encode('utf-8')
                )

            elif command.lower() == "put":
                resource_name = await aioconsole.ainput("Enter resource name to PUT to: ")
                value = await aioconsole.ainput("Enter value to PUT: ")

                payload = Message(
                    code=Code.PUT,
                    uri=f"coap://b.dtn.arpa/{resource_name}",
                    mtype=Type.NON,
                    mid=current_id,
                    payload=value.encode('utf-8')
                )

            elif command.lower() == "get":
                resource_name = await aioconsole.ainput("Enter resource name to GET: ")

                payload = Message(
                    code=Code.GET,
                    uri=f"coap://b.dtn.arpa/{resource_name}",
                    mtype=Type.NON,
                    mid=current_id,
                    payload=b"get"
                )

            elif command.lower() == "delete":
                resource_name = await aioconsole.ainput("Enter resource name to DELETE: ")

                payload = Message(
                    code=Code.DELETE,
                    uri=f"coap://b.dtn.arpa/{resource_name}",
                    mtype=Type.NON,
                    mid=current_id,
                    payload=b"delete"
                )

            else:
                print("Unknown command.")
                continue  # restart loop

            payload.opt.payload_length = len(payload.payload)
            payload.token = os.urandom(2)
            next_mid()

            encoded = payload.encode()
            coap_buffer.append(encoded)
            print(f"Queued {command.upper()} for {payload.get_request_uri()}, MID={payload.mid}, Token={payload.token.hex()}")

            if not flusher_task:
                flusher_task = asyncio.create_task(start_flusher())

            if len(coap_buffer) >= BUFFER_LIMIT:
                await flush_buffer()

    finally:
        if flusher_task:
            flusher_task.cancel()
        await send_client.disconnect()

async def chat_receive(receive_client):
    try:
        while True:
            adu_msg, recv_payload = await receive_client.receive_adu()
            print(f"\nReceived ADU from {adu_msg.src_eid}: {recv_payload}")

            response = Message.decode(recv_payload)

            print(f"Response:")
            print(f"  Code: {response.code}")
            print(f"  MID: {response.mid}")
            print(f"  Token: {response.token.hex() if response.token else 'None'}")
            print(f"  Payload: {response.payload.decode('utf-8', errors='ignore')}")
            print(f"  Mtype: {response.mtype}")

            await receive_client.send_response_status(aap2_pb2.ResponseStatus.RESPONSE_STATUS_SUCCESS)
    finally:
        await receive_client.disconnect()

# ----------------------------
# Entry Point
# ----------------------------

if __name__ == "__main__":
    asyncio.run(main(send_client, receive_client))
