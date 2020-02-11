import os
from collections import namedtuple
from typing import Optional

import vulkan as vk


class VulkanException(Exception):
    pass


QueueFamily = namedtuple('QueueFamily', 'graphics')
DeviceInfo = namedtuple('DeviceInfo', 'device, properties, features, queues, extensions')

VK_KHR_EXTERNAL_MEMORY_CAPABILITIES = 'VK_KHR_external_memory_capabilities'
VK_KHR_EXTERNAL_MEMORY = 'VK_KHR_external_memory'
VK_KHR_EXTERNAL_MEMORY_FD = 'VK_KHR_external_memory_fd'


class Device:
    """
    Wrapper about a Vulkan device.

    The first suitable Vulkan device is chosen.

    Args:
        app_name: Application name.
        debug: Enable Vulkan debugging.
    """
    def __init__(self, app_name: str, debug: bool = False):
        self.debug = debug
        self.vk_instance = None
        self.vk_device = None
        self.device_info = None
        self.instance_extensions = {ext.extensionName: ext.specVersion
                                    for ext in vk.vkEnumerateInstanceExtensionProperties(None)}
        print(f'vk instance extensions: {self.instance_extensions}')
        self._create_instance(app_name)
        device = self._find_device()
        self._initialize_device(device)
        print('vk device created')
        self._vkGetMemoryFdKHR = None

    def __del__(self):
        if self.vk_device is not None:
            vk.vkDestroyDevice(self.vk_device, None)
            print('vk device destroyed')
        if self.vk_instance is not None:
            vk.vkDestroyInstance(self.vk_instance, None)
            print('vk vk_instance destroyed')

    def is_device_suitable(self, info: DeviceInfo) -> bool:
        """
        Decide whether the device is suitable.

        Args:
            info: Device information.

        Returns:
            True if the device could be used, False otherwise.
        """
        return info.queues.graphics is not None and VK_KHR_EXTERNAL_MEMORY_FD in info.extensions

    def create_shared_image_memory(self, width: int, height: int) -> 'SharedImageMemory':
        """
        Create a shared image memory.

        Image format is VK_FORMAT_R8G8B8A8_UNORM.

        It can be imported in OpenGL and used as a backing store for textures.
        See `glCreateMemoryObjectsEXT`, `glImportMemoryFdEXT` and `glTexStorageMem2DEXT`.

        Args:
            width: The width to the image.
            height: The height to the image.

        Return:
            A wrapper around shared image memory.
        """
        return SharedImageMemory(self, width, height)

    def find_memory_type(self, type_bits, property_flags) -> Optional[int]:
        """
        Find memory type by type bits and property flags.

        Returns:
            Memory type index (it may be zero) on success, `None` on failure.
        """
        types = self._memory_properties.memoryTypes
        for i in range(vk.VK_MAX_MEMORY_TYPES):
            if (type_bits & 1) == 1 and types[i].propertyFlags & property_flags:
                return i
            type_bits >>= 1
        return None

    def get_fd_for_memory(self, vk_memory) -> int:
        """
        Get FD for shared memory.

        Args:
            vk_memory: Vulkan shared memory.

        Return:
             FD of the memory. Release it with `os.close`.
        """
        if self._vkGetMemoryFdKHR is None:
            self._load_vk_get_memory_fd_proc()

        vk_fd_info = vk.VkMemoryGetFdInfoKHR(
            memory=vk_memory,
            handleType=vk.VK_EXTERNAL_MEMORY_HANDLE_TYPE_OPAQUE_FD_BIT,
        )
        return self._vkGetMemoryFdKHR(self.vk_device, vk_fd_info)

    def _create_instance(self, app_name: str):
        """Create Vulkan instance."""
        app_info = vk.VkApplicationInfo(
            pApplicationName=app_name,
            applicationVersion=vk.VK_MAKE_VERSION(1, 0, 0),
            pEngineName='No Engine',
            engineVersion=vk.VK_MAKE_VERSION(1, 0, 0),
            apiVersion=vk.VK_API_VERSION_1_0,
        )

        if self.debug:
            # TODO: Check whether validation layers are supported
            layers = ['VK_LAYER_KHRONOS_validation']
        else:
            layers = []
        create_info = vk.VkInstanceCreateInfo(
            pApplicationInfo=app_info,
            ppEnabledExtensionNames=[VK_KHR_EXTERNAL_MEMORY_CAPABILITIES],
            ppEnabledLayerNames=layers
        )
        self.vk_instance = vk.vkCreateInstance(create_info, None)
        print('vk vk_instance created')

    def _find_device(self):
        """Find suitable Vulkan device."""
        vk_devices = vk.vkEnumeratePhysicalDevices(self.vk_instance)
        if not len(vk_devices):
            raise VulkanException('No vulkan devices available.')

        for vk_device in vk_devices:
            info = self._query_device_info(vk_device)
            if self.is_device_suitable(info):
                return info
        else:
            raise VulkanException('No suitable vulkan device found.')

    def _query_device_info(self, vk_physical_device):
        """Query device information."""
        properties_struct = vk.vkGetPhysicalDeviceProperties(vk_physical_device)
        properties = {key: getattr(properties_struct, key) for key in dir(properties_struct.obj)}
        print(f'properties: {properties}')
        features_struct = vk.vkGetPhysicalDeviceFeatures(vk_physical_device)
        features = {key for key in dir(features_struct) if getattr(features_struct, key)}
        print(f'features: {features}')
        queue_families = self._query_queue_families(vk_physical_device)
        print(f'queues: {queue_families}')
        extensions = {ext.extensionName: ext.specVersion
                      for ext in vk.vkEnumerateDeviceExtensionProperties(vk_physical_device, None)}
        print(f'extensions: {extensions}')
        return DeviceInfo(vk_physical_device, properties, features, queue_families, extensions)

    def _query_queue_families(self, vk_physical_device):
        """Query available device queue families."""
        graphics = None
        families = vk.vkGetPhysicalDeviceQueueFamilyProperties(vk_physical_device)
        for i, family in enumerate(families):
            if graphics is None and family.queueFlags & vk.VK_QUEUE_GRAPHICS_BIT:
                graphics = i

        return QueueFamily(graphics)

    def _initialize_device(self, info: DeviceInfo):
        """Initialize physical Vulkan device to get logical Vulkan device."""
        queue_families = info.queues
        queue_create_info = vk.VkDeviceQueueCreateInfo(
            queueFamilyIndex=queue_families.graphics,
            pQueuePriorities=[1.0],
        )
        device_features = vk.VkPhysicalDeviceFeatures()
        create_info = vk.VkDeviceCreateInfo(
            pQueueCreateInfos=[queue_create_info],
            pEnabledFeatures=device_features,
            ppEnabledExtensionNames=[VK_KHR_EXTERNAL_MEMORY, VK_KHR_EXTERNAL_MEMORY_FD],
        )
        self._memory_properties = vk.vkGetPhysicalDeviceMemoryProperties(info.device)
        self.device_info = info
        self.vk_device =  vk.vkCreateDevice(info.device, create_info, None)

    def _load_vk_get_memory_fd_proc(self):
        """Load vkGetMemoryFdKHR procedure."""
        proc = vk.vkGetDeviceProcAddr(self.vk_device, 'vkGetMemoryFdKHR')
        if not proc:
            raise VulkanException('Cannot load vkGetMemoryFdKHR.')
        self._vkGetMemoryFdKHR = proc


class SharedImageMemory:
    """
    Wrapper around Vulkan shared image memory.

    Use `fd` to import it in OpenGL.
    See `glCreateMemoryObjectsEXT`, `glImportMemoryFdEXT` and `glTexStorageMem2DEXT`.

    Properties:
        device: Device the memory is allocated in.
        width: Image width.
        height: Image height.
        size: Memory size.
        fd: Memory fd.
    """
    def __init__(self, device: Device, width: int, height: int):
        self.height = height
        self.width = width
        self.device = device
        self.size = None
        self.fd = None
        self.vk_image = None
        self.vk_image_memory = None
        self._create_image()
        self._create_image_memory()

    def __del__(self):
        if self.fd is not None:
            os.close(self.fd)
            print(f'vk vk_image_memory fd {self.fd} closed')
        if self.vk_image_memory is not None:
            vk.vkFreeMemory(self.device.vk_device, self.vk_image_memory, None)
            print('vk vk_image_memory destroyed')
        if self.vk_image is not None:
            vk.vkDestroyImage(self.device.vk_device, self.vk_image, None)
            print('vk vk_image destroyed')

    def _create_image(self):
        external_memory_image_create_info = vk.VkExternalMemoryImageCreateInfo(
            handleTypes=vk.VK_EXTERNAL_MEMORY_HANDLE_TYPE_OPAQUE_FD_BIT,
        )

        image_info = vk.VkImageCreateInfo(
            pNext=external_memory_image_create_info,
            imageType=vk.VK_IMAGE_TYPE_2D,
            extent=vk.VkExtent3D(
                width=self.width,
                height=self.height,
                depth=1,
            ),
            mipLevels=1,
            arrayLayers=1,
            format=vk.VK_FORMAT_R8G8B8A8_UNORM,
            tiling=vk.VK_IMAGE_TILING_OPTIMAL,
            samples=vk.VK_SAMPLE_COUNT_1_BIT,
            usage=vk.VK_IMAGE_USAGE_SAMPLED_BIT | vk.VK_IMAGE_USAGE_TRANSFER_SRC_BIT,
            sharingMode=vk.VK_SHARING_MODE_EXCLUSIVE,
            initialLayout=vk.VK_IMAGE_LAYOUT_UNDEFINED,
        )

        self.vk_image = vk.vkCreateImage(self.device.vk_device, image_info, None)
        print('vk vk_image created')

    def _create_image_memory(self):
        vk_device = self.device.vk_device
        dedicated_memory_info = vk.VkMemoryDedicatedAllocateInfo(
            pNext=None,
            image=self.vk_image,
            buffer=vk.VK_NULL_HANDLE,
        )

        memory_reqs = vk.vkGetImageMemoryRequirements(vk_device, self.vk_image)
        self.size = memory_reqs.size

        flags = vk.VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT | vk.VK_MEMORY_PROPERTY_HOST_COHERENT_BIT
        mem_type = self.device.find_memory_type(memory_reqs.memoryTypeBits, flags)
        if mem_type is None:
            flags = vk.VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT
            mem_type = self.device.find_memory_type(memory_reqs.memoryTypeBits, flags)
        if mem_type is None:
            raise VulkanException('Cannot find suitable memory type.')

        memory_info = vk.VkMemoryAllocateInfo(
            pNext=dedicated_memory_info,
            allocationSize=memory_reqs.size,
            memoryTypeIndex=mem_type,
        )
        self.vk_image_memory = vk.vkAllocateMemory(vk_device, memory_info, None)
        print('vk vk_image_memory created')

        self.fd = self.device.get_fd_for_memory(self.vk_image_memory)
        print(f'vk vk_image_memory fd {self.fd} obtained')
