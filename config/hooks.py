from urlwatch.reporters import TelegramReporter, ReporterBase, chunkstring
from urlwatch.filters import FilterBase

import logging
import requests

import pandas
import difflib
from io import StringIO


logger = logging.getLogger(__name__)


class ElectionCSVClean(FilterBase):

    __kind__ = "election_csv_clean"

    def filter(self, data, subfilter):
        sio = StringIO()
        for line in data.splitlines():
            sio.write(",".join(line.split(",")[:13]) + "\n")
        return sio.getvalue()

class TelegramElectionReporter(TelegramReporter):

    __kind__ = "election_tg"

    def _get_diff(self):

        for job_state in self.job_states:
            job = job_state.job
            if job.name != "main": continue

            old_data = str(job_state.old_data) if job_state.old_data else ""
            new_data = str(job_state.new_data) if job_state.new_data else ""

            if new_data == "": return

            sio = StringIO()

            for lineno, line in enumerate(difflib.unified_diff(old_data.splitlines(), new_data.splitlines())):
                if lineno < 3: continue
                if line.startswith("+"):
                    sio.write(line[1:])
            
            if not sio.getvalue().startswith("state"):
                sio = StringIO(new_data.splitlines()[0] + "\n" + sio.getvalue())
            
            sio.seek(0)

            df = pandas.read_csv(sio, header=0, sep=",")

            return df
                
    def _iter_update_texts(self):

        diff = self._get_diff()

        if diff is None: raise StopIteration

        for _, row in diff.iloc[:].iterrows():
            if row["new_votes"] == 0: continue
            row["leading_candidate_change"]  = row["new_votes"] * row["leading_candidate_partition"]
            row["trailing_candidate_change"] = row["new_votes"] * row["trailing_candidate_partition"]
            row["leading_candidate_percentage"] = 100.0 * row["leading_candidate_votes"] / (row["leading_candidate_votes"] + row["trailing_candidate_votes"])
            row["trailing_candidate_percentage"] = 100.0 * row["trailing_candidate_votes"] / (row["leading_candidate_votes"] + row["trailing_candidate_votes"])
            row["leading_candidate_partition_percentage"] = row["leading_candidate_partition"] * 100.0
            row["trailing_candidate_partition_percentage"] = row["trailing_candidate_partition"] * 100.0
            text = (
                "*{state}* ({new_votes:,.0f} new, {votes_remaining:,.0f} remaining)\n"
                "- *{leading_candidate_name}*  {leading_candidate_votes:8,.0f} ({leading_candidate_percentage:4.1f}%) ({leading_candidate_change:+6,.0f}, {leading_candidate_partition_percentage:.1f}%)\n"
                "- *{trailing_candidate_name}*  {trailing_candidate_votes:8,.0f} ({trailing_candidate_percentage:4.1f}%) ({trailing_candidate_change:+6,.0f}, {trailing_candidate_partition_percentage:.1f}%)\n"
                "*{leading_candidate_name}* is leading by *{vote_differential:,.0f}* votes."
            ).format_map(row)

            yield text
    
    def _escape_text(self, text: str) -> str:
        text = text.replace("(", "\\(", self.MAX_LENGTH)
        text = text.replace(")", "\\)", self.MAX_LENGTH)
        text = text.replace(".", "\\.", self.MAX_LENGTH)
        text = text.replace("-", "\\-", self.MAX_LENGTH)
        text = text.replace("+", "\\+", self.MAX_LENGTH)
        return text

    def submitToTelegram(self, bot_token, chat_id, text):
        logger.debug("Sending telegram request to chat id:'{0}'".format(chat_id))
        result = requests.post(
            "https://api.telegram.org/bot{0}/sendMessage".format(bot_token),
            data={"chat_id": chat_id, "text": text, "disable_web_page_preview": "true", "parse_mode": "MarkdownV2" })
        try:
            json_res = result.json()

            if (result.status_code == requests.codes.ok):
                logger.info("Telegram response: ok '{0}'. {1}".format(json_res['ok'], json_res['result']))
            else:
                logger.error("Telegram error: {0}".format(json_res['description']))
        except ValueError:
            logger.error(
                "Failed to parse telegram response. HTTP status code: {0}, content: {1}".format(result.status_code,
                                                                                                result.content))
        return result

    def submit(self):

        bot_token = self.config['bot_token']
        chat_ids = self.config['chat_id']
        chat_ids = [chat_ids] if isinstance(chat_ids, str) else chat_ids

        results = []

        for text in self._iter_update_texts():

            text = self._escape_text(text)

            if not text:
                logger.debug('Not calling telegram API (no changes)')
                return

            result = None
            for chunk in chunkstring(text, self.MAX_LENGTH, numbering=True):
                for chat_id in chat_ids:
                    res = self.submitToTelegram(bot_token, chat_id, chunk)
                    if res.status_code != requests.codes.ok or res is None:
                        results.append(res)

        return results