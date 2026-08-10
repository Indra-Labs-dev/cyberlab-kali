import os
import uuid

import docker
from docker.errors import NotFound

import registry
from schema import LabInstance

LABEL_MANAGED = "cyberlab.lab"
LABEL_ID = "cyberlab.lab.id"
LABEL_DEFINITION = "cyberlab.lab.definition"
LABEL_DISPLAY_NAME = "cyberlab.lab.display_name"
LABEL_NETWORK = "cyberlab.lab.network"
LABEL_PORT = "cyberlab.lab.internal_port"

KALI_NETWORK_NAME = os.environ.get("KALI_NETWORK_NAME", "cyberlab-kali-net")

client = docker.from_env()


class LabNotFoundError(LookupError):
    pass


def _network_name(lab_id: str) -> str:
    return f"cyberlab-lab-{lab_id}"


def _container_name(definition_name: str, lab_id: str) -> str:
    return f"cyberlab-lab-{definition_name}-{lab_id}"


def _to_instance(container) -> LabInstance:
    container.reload()
    labels = container.labels
    host_port = None
    internal_port = int(labels.get(LABEL_PORT, 0)) or None
    if internal_port:
        bindings = container.attrs.get("NetworkSettings", {}).get("Ports", {}).get(f"{internal_port}/tcp")
        if bindings:
            host_port = int(bindings[0]["HostPort"])

    return LabInstance(
        id=labels.get(LABEL_ID, ""),
        definition=labels.get(LABEL_DEFINITION, ""),
        display_name=labels.get(LABEL_DISPLAY_NAME, ""),
        status=container.status,
        container_name=container.name,
        host_port=host_port,
        internal_port=internal_port,
        network=labels.get(LABEL_NETWORK),
        created_at=container.attrs.get("Created"),
    )


def _find_container(lab_id: str):
    containers = client.containers.list(all=True, filters={"label": f"{LABEL_ID}={lab_id}"})
    if not containers:
        raise LabNotFoundError(f"no lab found with id {lab_id}")
    return containers[0]


def list_labs() -> list[LabInstance]:
    containers = client.containers.list(all=True, filters={"label": f"{LABEL_MANAGED}=true"})
    return [_to_instance(c) for c in containers]


def get_lab(lab_id: str) -> LabInstance:
    return _to_instance(_find_container(lab_id))


def _run_container(definition_name: str, lab_id: str, network_name: str):
    definition = registry.get_definition(definition_name)
    container_name = _container_name(definition_name, lab_id)

    container = client.containers.run(
        definition.image,
        name=container_name,
        detach=True,
        network=network_name,
        ports={f"{definition.internal_port}/tcp": ("127.0.0.1", None)},
        labels={
            LABEL_MANAGED: "true",
            LABEL_ID: lab_id,
            LABEL_DEFINITION: definition_name,
            LABEL_DISPLAY_NAME: definition.display_name,
            LABEL_NETWORK: network_name,
            LABEL_PORT: str(definition.internal_port),
        },
        mem_limit="512m",
        security_opt=["no-new-privileges:true"],
    )

    try:
        kali_network = client.networks.get(KALI_NETWORK_NAME)
        kali_network.connect(container)
    except NotFound:
        pass  # kali network not present (e.g. running labmanager standalone in tests)

    return container


def create_lab(definition_name: str) -> LabInstance:
    registry.get_definition(definition_name)  # raises LabDefinitionNotFoundError if unknown
    lab_id = uuid.uuid4().hex[:8]
    network_name = _network_name(lab_id)

    client.networks.create(network_name, driver="bridge")
    container = _run_container(definition_name, lab_id, network_name)
    return _to_instance(container)


def start_lab(lab_id: str) -> LabInstance:
    container = _find_container(lab_id)
    container.start()
    return _to_instance(container)


def stop_lab(lab_id: str) -> LabInstance:
    container = _find_container(lab_id)
    container.stop(timeout=10)
    return _to_instance(container)


def reset_lab(lab_id: str) -> LabInstance:
    """Stop, remove, and recreate the container from a clean image — wipes
    any state the lab accumulated (e.g. a DVWA database), while keeping the
    same lab id, network, and published port identity where possible.
    """
    container = _find_container(lab_id)
    labels = container.labels
    definition_name = labels[LABEL_DEFINITION]
    network_name = labels[LABEL_NETWORK]

    container.stop(timeout=10)
    container.remove()
    new_container = _run_container(definition_name, lab_id, network_name)
    return _to_instance(new_container)


def delete_lab(lab_id: str) -> None:
    container = _find_container(lab_id)
    network_name = container.labels.get(LABEL_NETWORK)

    container.stop(timeout=10)
    container.remove()

    if network_name:
        try:
            client.networks.get(network_name).remove()
        except NotFound:
            pass
