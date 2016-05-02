
import abc

__all__ = ["UpnpAbstractBackend"]


class UpnpAbstractBackend(object):
    __metaclass__ = abc.ABCMeta

    def __init__(self, client_key, uuid, version, model_id, ipaddr,
                 metadata=None, options=None):
        self.client_key = client_key
        self.uuid = uuid
        self.version = version
        self.model_id = model_id
        self.ipaddr = ipaddr

    @classmethod
    def support_device(cls, model_id, version):
        return False

    @abc.abstractmethod
    def connect(self):
        pass

    @abc.abstractmethod
    def close(self):
        pass

    @abc.abstractmethod
    def add_trust(self):
        pass

    @abc.abstractmethod
    def rename(self, new_device_name):
        pass

    @abc.abstractmethod
    def modify_password(self, old_password, new_password, reset_acl):
        pass

    @abc.abstractmethod
    def modify_network(self, network_options):
        pass

    @abc.abstractmethod
    def get_wifi_list(self):
        pass


class UpnpError(RuntimeError):
    def __init__(self, *args, **kw):
        super(UpnpError, self).__init__(*args)
        if "err_symbol" in kw:
            self.err_symbol = kw["err_symbol"]
        else:
            self.err_symbol = ("UNKNOWN_ERROR")


def NotSupportError(model_id, version):  # noqa
    return UpnpError(
        "Device '%s' with '%s' is not supported" % (model_id, version),
        err_symbol=("NOT_SUPPORT", ))


def AuthError(reason):  # noqa
    return UpnpError(reason, err_symbol=("AUTH_ERROR",))


def TimeoutError():  # noqa
    return UpnpError("Connection timeout", err_symbol=("TIMEOUT", ))


def ConnectionBroken():  # noqa
    return UpnpError("Connection broken", err_symbol=("CONNECTION_BROKEN", ))