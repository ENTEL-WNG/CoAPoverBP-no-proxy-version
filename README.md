## RUNNING THE PROJECT FOR THE FIRST TIME:

```bash
make posix
sudo apt install python3-pip
sudo pip install ud3tn
sudo pip install aiocoap
sudo pip install aioconsole
```

## IF YOU ENCOUTER THE ERROR "make[1]: Nothing to be done for 'posix'.", RUN:

```bash
make clean
make posix
```

## FOR EACH DEPLOYMENT, INSIDE THE UD3TN FOLDER RUN:

```bash
build/posix/ud3tn --node-id dtn://a.dtn/ --aap-port 4242 --aap2-socket ud3tn-a.aap2.socket --cla "tcpclv3:*,4556"
```

```bash
build/posix/ud3tn --node-id dtn://b.dtn/ --aap-port 4243 --aap2-socket ud3tn-b.aap2.socket --cla "tcpclv3:*,4225"
```

```bash
build/posix/ud3tn --node-id dtn://c.dtn/ --aap-port 4244 --aap2-socket ud3tn-c.aap2.socket --cla "sqlite:ud3tn-c.sqlite;tcpclv3:*,4557" --external-dispatch
```

```bash
aap2-bdm-ud3tn-routing -vv --socket ud3tn-c.aap2.socket
```

```bash
build/posix/ud3tn --node-id dtn://d.dtn/ --aap-port 4245 --aap2-socket ud3tn-d.aap2.socket --cla "tcpclv3:*,4558"
```

```bash
aap2-config --socket ud3tn-a.aap2.socket --schedule 1 600 100000 dtn://c.dtn/ --reaches dtn://b.dtn/ --reaches dtn://d.dtn/  tcpclv3:localhost:4557
aap2-config --socket ud3tn-c.aap2.socket --schedule 30 600 100000 dtn://d.dtn/ --reaches dtn://b.dtn/ tcpclv3:localhost:4558 
aap2-config --socket ud3tn-d.aap2.socket --schedule 1 600 100000 dtn://c.dtn/ --reaches dtn://a.dtn/ tcpclv3:localhost:4557
aap2-config --socket ud3tn-d.aap2.socket --reaches dtn://b.dtn/rec --schedule 1 600 100000  dtn://b.dtn/ tcpclv3:localhost:4225
aap2-config --socket ud3tn-c.aap2.socket --reaches dtn://a.dtn/rec --schedule 1 600 100000 dtn://a.dtn/ tcpclv3:localhost:4556 
aap2-config --socket ud3tn-b.aap2.socket --schedule 1 600 100000 dtn://d.dtn/ --reaches dtn://c.dtn/ --reaches dtn://a.dtn/ tcpclv3:localhost:4558
```

```bash
python3 NodeAaap2.py
```

```bash
python3 NodeBaap2.py
```

## TO INTERACT WITH THE BDM AND PERSISTENT STORAGE ON NODE C, CHECK:

```bash
sqlite3 ud3tn-c.sqlite \
  "SELECT * FROM bundles;"

sqlite3 ud3tn-c.sqlite \
  "SELECT COUNT(*) FROM bundles;"

sqlite3 ud3tn-c.sqlite \
  "DELETE FROM bundles WHERE creation_timestamp = ;"

aap2-storage-agent --socket ud3tn-c.aap2.socket --storage-agent-eid "dtn://c.dtn/sqlite" push --dest-eid-glob "*"
```

## CURRENT PROGRESS OF THIS IMPLEMENTATION

This implemenation currently has a CoAP Client in the same instance as the Node A Application Agent and a CoAP Server along the Node B Application Agent. It sends CoAP NON PUT messages over the Bunlde Network passing multiple Bundle Nodes, implementing persisent storage functionality and delayed contact simulation.

The Topology looks as follows:

+-------------+      +--------+      +--------+      +-------------+
| CoAP Client |      | SQLLite|      |        |      | CoAP Server |
+-------------+      |   BDM  |      |        |      +-------------+
|     BP      | ---> |   BP   | ---> |   BP   | ---> |      BP     |
+-------------+      +--------+      +--------+      +-------------+

     Node A            Node C          Node D             Node B

If displayed wrong, refer to Topology.png
                                     
## TODO

- [ ] Utilize aiocoaps internal token and MID handlingn, where applicable.
- [ ] Modify the aiocoap library code for the message id overflow scenario.
- [ ] Handle CON messages and the corresponding retransmissions correctly.
- [ ] Handle other message types correctly

## AUTHORS:


## FUNDING:
This research was funded in part by the Spanish MCIU/AEI/10.13039/501100011033/ FEDER/UE through project PID2023-146378NB-I00, and by Secretaria d'Universitats i Recerca del departament d'Empresa i Coneixement de la Generalitat de Catalunya with the grant number 2021 SGR 00330


