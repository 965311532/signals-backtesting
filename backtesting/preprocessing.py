import hermes
import json
import pytz
import pandas as pd
from typing import List
from flatten_json import flatten
import arrow
import logging

logging.basicConfig()
log = logging.getLogger('preprocessing')
log.setLevel(logging.DEBUG)
logging.getLogger('hermes').setLevel(logging.WARNING)

class TelegramChatPreprocessor:
    def __init__(self, tz_messages=pytz.timezone("Europe/Rome")):
        self.tz_messages = tz_messages

    def prepare_json(self, json_path: str) -> List[tuple]:
        """Takes in a the messy telegram json, flatten it and keep relevant data"""

        with open(json_path, "r", encoding="utf8") as f:
            data = json.loads(f.read())

        # use flatten module to unnest values
        raw_data = [flatten(d) for d in data["messages"]]

        # it's easier to manipulate with pandas
        df = pd.DataFrame(raw_data)

        # merges different nesting-level texts
        text_cols = df.columns.intersection(
            [f"text_{i}" for i in range(0, 100)]
            + [f"text_{i}_text" for i in range(0, 100)]
        )

        df["agg_text"] = (
            df.text.fillna("").str.cat(df[text_cols].fillna(""), sep=" ").str.strip()
        )

        # drops empty rows
        df.drop(df[df["agg_text"].str.strip() == ""].index, inplace=True)

        # last fix-ups
        df["text"] = df["agg_text"]
        df["time"] = pd.to_datetime(df["date"]).dt.tz_localize(self.tz_messages)

        df.reset_index(inplace=True, drop=True)

        # the python dict is a bit faster to iterate over
        return list(df[["time", "text"]].itertuples())

    def preprocess(self, data: List[tuple], to: str = None) -> List[dict]:
        result = list()
        for piece in data:
            new_piece = dict(id=piece.Index, time=arrow.get(piece.time), text=piece.text)
            try:
                new_piece['interpretation'] = hermes.interpret(piece.text)
                result.append(new_piece)
            except hermes.TooManyFeatures as e:
                log.debug(f'{e=}')
                continue
        return result

def preprocess(json_path, tz_messages=pytz.timezone("Europe/Rome")):
    prep = TelegramChatPreprocessor()
    data = prep.prepare_json(json_path)
    return prep.preprocess(data)


def main():
    print(preprocess("../chats/results_daniel.json"))


if __name__ == "__main__":
    main()
