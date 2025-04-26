# AAP2 client libraries and definitions
from ud3tn_utils.aap2.aap2_client import AAP2AsyncUnixClient 
from ud3tn_utils.aap2.generated import aap2_pb2

# Async/CoAP libraries
import asyncio
import sys
import os
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'aiocoap', 'src'))
sys.path.insert(0, project_root)
import aiocoap
from aiocoap.message import Message
from aiocoap.numbers.types import Type
import aiocoap.resource as resource

# ----------------------------
# CoAP Resources Definitions
# ----------------------------

class TemperatureResource(resource.Resource):
    def __init__(self):
        super().__init__()
        self.temperatures = []
        
    async def render_put(self, request):
        try:
            temperature = float(request.payload.decode("utf-8"))
            self.temperatures.append(temperature)
            print(f"Received temperature: {temperature}")
            return aiocoap.Message(code=aiocoap.CHANGED, payload=b"Temperature recorded.")
        except ValueError:
            return aiocoap.Message(code=aiocoap.BAD_REQUEST, payload=b"Invalid temperature.")

class DummyPOST(resource.Resource):
    def __init__(self):
        super().__init__()

    
# ----------------------------
# AAP2 + CoAP Server Handling
# ----------------------------

SERVER_ADDRESS = 'ud3tn-b.aap2.socket'

# Instantiate AAP2 clients for send and receive roles
send_client = AAP2AsyncUnixClient(SERVER_ADDRESS)
receive_client = AAP2AsyncUnixClient(SERVER_ADDRESS)

# Resource table for handling requests by URI path
resources = {}

async def main():
    # Register static CoAP resources
    temp_resource = TemperatureResource()
    post_resource = DummyPOST()
    
    resources['temperature'] = temp_resource
    resources[''] = post_resource  # Fallback or root path resource
    
    async with send_client, receive_client:
        await send_client.configure(agent_id='snd')
        await receive_client.configure(agent_id='rec', subscribe=True)
        
        # Start main CoAP-over-BP handling loop
        await bundle_coap_server(receive_client, send_client, resources)

async def bundle_coap_server(receive_client, send_client, resources):
    """Main loop: receive CoAP requests over BP, dispatch to resources, send responses."""
    try:
        while True:
            adu_msg, recv_payload = await receive_client.receive_adu()
            print(f"Received ADU from {adu_msg.src_eid}: {len(recv_payload)} bytes")

            await receive_client.send_response_status(
                aap2_pb2.ResponseStatus.RESPONSE_STATUS_SUCCESS
            )

            offset = 0
            while offset < len(recv_payload):
                partial = recv_payload[offset:]
                try:
                    msg = Message.decode(partial)

                    if not msg.opt.payload_length:
                        raise ValueError("Missing Payload-Length option in incoming CoAP message")

                    payload_length = msg.opt.payload_length

                    encoded = msg.encode()
                    payload_marker_index = encoded.find(b'\xFF')
                    if payload_marker_index == -1:
                        raise ValueError("Payload Marker (0xFF) not found!")

                    full_message_length = payload_marker_index + 1 + payload_length

                    coap_bytes = recv_payload[offset:offset + full_message_length]
                    offset += full_message_length

                    # Decode full message now
                    request = Message.decode(coap_bytes)

                    print(f"Parsed CoAP request: MID={request.mid} Token={request.token.hex()} Code={request.code} Payload Length={request.opt.payload_length}")

                    path = request.opt.uri_path
                    resource_name = path[0] if path else ''

                    # Dispatch to resource
                    if resource_name in resources:
                        resource = resources[resource_name]
                        if request.code == aiocoap.PUT:
                            handler = resource.render_put
                        else:
                            response = aiocoap.Message(code=aiocoap.METHOD_NOT_ALLOWED, payload=b"Method not allowed")
                            handler = None

                        if handler:
                            try:
                                response = await handler(request)
                            except Exception as e:
                                print(f"Error during resource handling: {e}")
                                response = aiocoap.Message(code=aiocoap.INTERNAL_SERVER_ERROR, payload=b"Internal server error")

                    else:
                        response = aiocoap.Message(code=aiocoap.NOT_FOUND, payload=b"Resource not found")

                    # Set metadata from original request
                    response.token = request.token
                    response.mid = request.mid
                    response.mtype = Type.ACK if request.mtype != Type.NON else Type.NON

                    payload = response.encode()
                    await send_client.send_adu(
                        aap2_pb2.BundleADU(
                            dst_eid="dtn://a.dtn/rec",
                            payload_length=len(payload)
                        ),
                        payload,
                    )
                    await send_client.receive_response()

                except Exception as e:
                    print(f"Failed to parse CoAP message from aggregation: {e}")
                    break

    finally:
        await receive_client.disconnect()
        await send_client.disconnect()

# Run main entry point
if __name__ == "__main__":
    asyncio.run(main())