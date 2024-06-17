import re
import string
import discord
from typing import Optional
from discord import app_commands
from discord.ext import commands

# xl_column_name is modified from https://github.com/jmcnamara/XlsxWriter/blob/172211873cd2fabe67876722a523b9bf9771d613/xlsxwriter/utility.py#L174-L211
# SPDX-License-Identifier: BSD-2-Clause
# Copyright 2013-2024, John McNamara, jmcnamara@cpan.org

def xl_column_name(col):
	col_num = col
	if col_num < 0:
		raise ValueError(f"Col number {col} must be >= 0")

	col_num += 1  # Change to 1-index.
	col_str = ""

	while col_num:
		# Set remainder from 1 .. 26
		remainder = col_num % 26

		if remainder == 0:
			remainder = 26

		# Convert the remainder to a character.
		col_letter = chr(ord("A") + remainder - 1)

		# Accumulate the column letters, right to left.
		col_str = col_letter + col_str

		# Get the next order of magnitude.
		col_num = int((col_num - 1) / 26)

	return col_str

def prefixed(candidates: list[str]):
	for i, candidate in enumerate(candidates):
		if candidate:
			yield f'{xl_column_name(i)}) {candidate}'

def prefix_to_candidate_name(candidates: list[str], prefix: str):
	"""
	>>> prefix_to_candidate_name(['Lenin', 'Stalin', 'Mao'], 'C')
	'Mao'
	"""
	for i, c in enumerate(candidates):
		if xl_column_name(i) == prefix:
			return c
	raise ValueError('Prefix not found in the candidate list')

class ElectionCreateModal(discord.ui.Modal, title='Create new election'):
	options = discord.ui.TextInput(
		label='Candidates, one per line',
		required=True,
		style=discord.TextStyle.long,
		min_length=1,
		max_length=2000,
	)

	def __init__(self, cog, election_title):
		super().__init__()
		self.cog = cog
		self.election_title = election_title

	async def on_submit(self, interaction):
		assert interaction.guild_id is not None
		self.text = str(self.options)
		candidates = self.text.splitlines()

		election_id = await self.cog.db.create_election(
			guild_id=interaction.guild_id,
			creator_id=interaction.user.id,
			candidate_names=candidates,
		)

		view = discord.ui.View(timeout=None)
		view.add_item(VoteButton(election_id))
		view.add_item(ResultsButton(election_id, finalized=False))
		view.add_item(FinalizeButton(election_id))

		options = '\n'.join(prefixed(candidates))
		if self.election_title is not None:
			text = f'# {self.election_title}\n{options}'
		else:
			text = options

		await interaction.response.send_message(text, view=view)

class BallotModal(discord.ui.Modal, title='Vote on an election'):
	ballot = discord.ui.TextInput(
		label='Candidates, in vote order, one per line',
		required=True,
		style=discord.TextStyle.long,
		min_length=1,
		max_length=2000,
	)

	def __init__(self, db, election_id, text):
		super().__init__()
		self.db = db
		self.election_id = election_id
		self.ballot.default = text

	async def on_submit(self, interaction):
		self.interaction = interaction
		assert interaction.guild_id is not None
		self.text = str(self.ballot)

		candidate_names = await self.db.get_candidate_names(self.election_id)
		candidates = [
			[prefix_to_candidate_name(candidate_names, line.partition(')')[0].strip())]
			for line
			in self.text.upper().splitlines()
		]
		await self.db.submit_ballot(election_id=self.election_id, user_id=interaction.user.id, ballot=candidates)
		await interaction.response.send_message('Thanks for voting!', ephemeral=True)

class VoteButton(
	discord.ui.DynamicItem[discord.ui.Button],
	template=r'election:(\d+)',
):
	def __init__(self, election_id):
		self.election_id = election_id
		super().__init__(discord.ui.Button(
			label='Vote',
			style=discord.ButtonStyle.primary,
			custom_id=f'election:{election_id}',
			emoji='🗳️',
		))

	@classmethod
	async def from_custom_id(cls, interaction, item, match: re.Match[str]):
		return cls(int(match[1]))

	async def callback(self, interaction):
		db = interaction.client.cogs['Database']
		if await db.check_if_voted(user_id=interaction.user.id, election_id=self.election_id):
			await interaction.response.send_message('You have already voted on that election.', ephemeral=True)
		else:
			default = interaction.message.content
			# get rid of the title if necessary
			# this is faster than querying the db for the candidate names and formatting them anew
			if default.startswith('# '):
				default = '\n'.join(default.splitlines()[1:])

			await interaction.response.send_modal(BallotModal(db, self.election_id, default))

class ResultsButton(
	discord.ui.DynamicItem[discord.ui.Button],
	template=r'results:(\d+):finalized:([01])',
):
	def __init__(self, election_id, *, finalized: bool):
		self.election_id = election_id
		self.finalized = finalized
		super().__init__(discord.ui.Button(
			label='See results',
			style=discord.ButtonStyle.primary,
			custom_id=f'results:{election_id}:finalized:{int(finalized)}',
			emoji='🥇',
		))

	@classmethod
	async def from_custom_id(cls, interaction, item, match: re.Match[str]):
		return cls(int(match[1]), finalized=match[2] == '1')

	async def callback(self, interaction):
		db = interaction.client.cogs['Database']
		results = await db.get_results(self.election_id)
		if self.finalized and not results:
			await interaction.response.send_message('🦗 Bummer… nobody voted on this election.')
			return

		if not self.finalized and not await db.check_if_voted(user_id=interaction.user.id, election_id=self.election_id):
			await interaction.response.send_message(
				'To prevent strategic voting, you may only see results on elections *after* voting on them.',
				ephemeral=True,
			)
			return

		results = await db.get_results(self.election_id)
		await interaction.response.send_message('\n'.join(self.format_results(results)), ephemeral=not self.finalized)

	@classmethod
	def format_results(cls, results):
		rank = 1
		for l in results:
			for candidate in l:
				yield fr'{rank}\. {candidate}'
			rank += 1

class FinalizeButton(
	discord.ui.DynamicItem[discord.ui.Button],
	template=r'finalize:(\d+)',
):
	def __init__(self, election_id):
		self.election_id = election_id
		super().__init__(discord.ui.Button(
			label='Finalize election',
			style=discord.ButtonStyle.primary,
			custom_id=f'finalize:{election_id}',
			emoji='✅',
		))

	@classmethod
	async def from_custom_id(cls, interaction, item, match: re.Match[str]):
		return cls(int(match[1]))

	async def callback(self, interaction):
		if (
			interaction.message.interaction_metadata.user != interaction.user
			and not interaction.channel.permissions_for(interaction.user).manage_messages
		):
			await interaction.response.send_message(
				'You must have created the election or have Manage Messages permissions to close an election.',
				ephemeral=True,
			)
			return

		view = discord.ui.View(timeout=None)
		view.add_item(ResultsButton(self.election_id, finalized=True))
		await interaction.message.edit(view=view)

class Elector(commands.Cog):
	def __init__(self, bot):
		self.bot = bot
		self.db = bot.cogs['Database']

	async def cog_load(self):
		self.bot.add_dynamic_items(VoteButton, ResultsButton, FinalizeButton)

	@app_commands.command()
	async def election(self, interaction, title: Optional[str] = None):
		modal = ElectionCreateModal(self, title)
		await interaction.response.send_modal(modal)

async def setup(bot):
	await bot.add_cog(Elector(bot))
