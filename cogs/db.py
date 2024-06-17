import discord
import asyncpg
from discord.ext import commands
from schulze import compute_ranks

class Database(commands.Cog):
	def __init__(self, bot):
		self.bot = bot
		self.queries = bot.queries('db.sql')

	async def create_election(self, *, guild_id: int, creator_id: int, candidate_names: list[str]):
		return await self.bot.pool.fetchval(
			self.queries.create_election(),
			guild_id,
			creator_id,
			candidate_names,
		)

	async def submit_ballot(self, *, election_id: int, user_id: int, ballot: list[list[str]]):
		try:
			await self.bot.pool.execute(self.queries.submit_ballot(), election_id, user_id, ballot)
		except asyncpg.UniqueViolationError:
			raise commands.UserInputError('You have already voted in this election.')

	async def get_candidate_names(self, election_id: int):
		return await self.bot.pool.fetchval(self.queries.get_candidate_names(), election_id)

	async def check_if_voted(self, *, election_id: int, user_id: int):
		return await self.bot.pool.fetchval(self.queries.check_if_voted(), user_id, election_id)

	async def get_ballots(self, election_id):
		return await self.bot.pool.fetch(self.queries.get_ballots(), election_id)

	async def get_results(self, election_id):
		ballots = [
			(record['ballot'], record['weight'])
			for record
			in await self.get_ballots(election_id)
		]
		if not ballots:
			return []
		candidate_names = await self.get_candidate_names(election_id)
		return compute_ranks(candidate_names, ballots)

async def setup(bot):
	await bot.add_cog(Database(bot))
