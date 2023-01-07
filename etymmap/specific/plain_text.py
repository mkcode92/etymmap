import abc
from typing import Union

import wikitextparser as wtp


class PlainTextMapperABC(abc.ABC):
    @abc.abstractmethod
    def __call__(
        self, element: Union[str, wtp.WikiText], recursive: bool = True, join=" "
    ) -> str:
        pass
