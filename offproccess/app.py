from offproccess.vulkan import Device


def run():
    device = Device('Demo', True)
    memory = device.create_shared_image_memory(100, 200)
    semaphore = device.create_shared_semaphore()
    del semaphore
    del memory
    del device
