#!/usr/bin/env python

import jinja2
import bot_bin.bot
import qtoml as toml

class Elector(bot_bin.bot.Bot):
	def __init__(self, **kwargs):
		super().__init__(**kwargs, setup_db=True)
		self.jinja_env = jinja2.Environment(
			loader=jinja2.FileSystemLoader('sql'),
			line_statement_prefix='-- :',
		)

	def queries(self, template_name):
		return self.jinja_env.get_template(template_name).module

	startup_extensions = [
		'jishaku',
		'bot_bin.misc',
		'bot_bin.debug',
		'bot_bin.sql',
		'bot_bin.systemd',
		'cogs.db',
		'cogs.elector',
	]

if __name__ == '__main__':
	with open('config.toml') as f:
		config = toml.load(f)
		Elector(config=config).run()
