# AAP2 client libraries and definitions
from ud3tn_utils.aap2.aap2_client import AAP2AsyncUnixClient 
from ud3tn_utils.aap2.generated import aap2_pb2

# Async/CoAP libraries
import asyncio
from aiocoap.message import Message
from aiocoap.numbers.codes import Code
import aiocoap
import aiocoap.resource as resource
from aiocoap.numbers.contentformat import ContentFormat

# ----------------------------
# CoAP Resources Definitions
# ----------------------------

class TemperatureResource(resource.Resource):
    """CoAP resource to GET latest/all temperatures or PUT new readings."""
    def __init__(self):
        super().__init__()
        self.temperatures = []
        
    async def render_get(self, request):
        if "all" in request.opt.uri_query:
            print("GET all")
            payload = ", ".join(map(str, self.temperatures)).encode("utf-8")
        else:
            print("GET 1")
            payload = (
                str(self.temperatures[-1]).encode("utf-8")
                if self.temperatures
                else b"No temperatures recorded."
            )
        return aiocoap.Message(payload=payload)
        
    async def render_put(self, request):
        try:
            temperature = float(request.payload.decode("utf-8"))
            self.temperatures.append(temperature)
            print(f"Received temperature: {temperature}")
            return aiocoap.Message(code=aiocoap.CHANGED, payload=b"Temperature recorded.")
        except ValueError:
            return aiocoap.Message(code=aiocoap.BAD_REQUEST, payload=b"Invalid temperature.")

class DummyPOST(resource.Resource):
    """A placeholder POST-only CoAP resource."""
    def __init__(self):
        super().__init__()
        
    async def render_post(self, request):
        print(request)
        return aiocoap.Message(code=aiocoap.CHANGED, payload=b"POST.")

class DynamicResourceCreator(resource.Resource):
    """Creates new resources dynamically based on POSTed requests."""
    def __init__(self, root_site):
        super().__init__()
        self.root_site = root_site
        
    async def render_post(self, request):
        resource_id = request.opt.uri_path[-1]
        if resource_id in self.root_site._resources:
            return aiocoap.Message(payload=b"The resource already exists.", code=aiocoap.FORBIDDEN)
        payload = request.payload.decode('utf-8')
        new_resource = DynamicResource(initial_data=payload)
        self.root_site.add_resource((resource_id,), new_resource)
        return aiocoap.Message(payload=f"Resource '{resource_id}' created.".encode('utf-8'), code=aiocoap.CREATED)

class DynamicResource(resource.Resource):
    """A generic CoAP resource whose data can be extended via POST."""
    def __init__(self, initial_data=""):
        super().__init__()
        self.data = initial_data
        
    async def render_get(self, request):
        return aiocoap.Message(payload=self.data.encode('utf-8'), code=aiocoap.CONTENT)
        
    async def render_post(self, request):
        payload = request.payload.decode('utf-8')
        self.data += f"\n{payload}"
        return aiocoap.Message(payload=b"Data added.", code=aiocoap.CHANGED)
    
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
            # Wait for incoming CoAP-over-BP ADU
            adu_msg, recv_payload = await receive_client.receive_adu()
            print(f"Received ADU from {adu_msg.src_eid}: {recv_payload}")

            # Acknowledge receipt to ud3tn
            await receive_client.send_response_status(
                aap2_pb2.ResponseStatus.RESPONSE_STATUS_SUCCESS
            )

            # Decode the CoAP message from the received payload
            request = Message.decode(recv_payload)
            print(f"Decoded CoAP request: {request}")
            
            path = request.opt.uri_path
            resource_name = path[0] if path else ''
            
            print(f"Accessing resource: '{resource_name}'")
            
            # Dispatch based on URI path
            if resource_name in resources:
                resource = resources[resource_name]
                
                # Choose appropriate method handler
                if request.code == aiocoap.GET:
                    handler = resource.render_get
                elif request.code == aiocoap.PUT:
                    handler = resource.render_put
                elif request.code == aiocoap.POST:
                    handler = resource.render_post
                else:
                    response = aiocoap.Message(code=aiocoap.METHOD_NOT_ALLOWED, 
                                             payload=f"Method not allowed".encode('utf-8'))
                    handler = None
                
                # Call the resource method and build response
                if handler:
                    try:
                        response = await handler(request)
                    except Exception as e:
                        print(f"Error processing request: {e}")
                        response = aiocoap.Message(code=aiocoap.INTERNAL_SERVER_ERROR, 
                                                 payload=f"Internal server error: {str(e)}".encode('utf-8'))
            else:
                # Unknown resource path
                print(f"Resource not found: {resource_name}")
                response = aiocoap.Message(code=aiocoap.NOT_FOUND, 
                                         payload=f"Resource not found: {resource_name}".encode('utf-8'))
            
            # Echo back original CoAP metadata
            response.token = request.token
            response.mid = request.mid
            response.mtype = request.mtype
            
            # Send CoAP response wrapped in a Bundle Protocol ADU
            print("CoAP Response to be sent back:")
            print(f"  Code: {response.code}")
            print(f"  Token: {response.token.hex() if response.token else 'None'}")
            print(f"  Payload: {response.payload}")
            
            payload = response.encode()
            await send_client.send_adu(
                aap2_pb2.BundleADU(
                    dst_eid="dtn://a.dtn/rec", # Send it back to the original CoAP client
                    payload_length=len(payload)
                ),
                payload,
            )

            # Wait for confirmation from ud3tn
            resp = await send_client.receive_response()
            print("Send status:", resp)

    finally:
        await receive_client.disconnect()
        await send_client.disconnect()

# Run main entry point
if __name__ == "__main__":
    asyncio.run(main())