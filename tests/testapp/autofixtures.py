# -*- coding: utf-8 -*-

import random
from datetime import timedelta, date

from django.contrib.auth import get_user_model

from tests.testapp.models import Author, Publisher, Book, Store
from autofixture import generators, register, AutoFixture


class PublisherGenerator(generators.Generator):
    publishers = [
        'Addison-Wesley', 'Aladdin Paperbacks', 'Anvil Press Poetry',
        'Basic Books', 'Blackstaff Press', 'Blake Publishing', 'Butterworth-Heinemann',
        'Cambridge University Press', 'Century', 'Crocker & Brewster',
        'Dedalus Books', 'Dick and Fitzgerald', 'Dorchester Publishing',
        'Fairview Press', 'Four Walls Eight Windows'
    ]

    def generate(self):
        return random.choice(self.publishers)


class UserGenerator(generators.Generator):

    USER_MODEL = get_user_model()

    def generate(self):
        defaults = {
            self.USER_MODEL.USERNAME_FIELD: '{name}{num1}{num2}'.format(
                name=generators.LastNameGenerator().generate(),
                num1=generators.SmallIntegerGenerator().generate(),
                num2=generators.SmallIntegerGenerator().generate()
            ).lower(),
            'password': generators.StringGenerator(min_length=8, max_length=16).generate()
        }
        return self.USER_MODEL.objects.create_user(**defaults)


class AuthorFixture(AutoFixture):
    field_values = {
        'user': UserGenerator(),
        'name': generators.FirstNameGenerator(),
        'age': generators.PositiveIntegerGenerator(min_value=20, max_value=80)
    }
register(Author, AuthorFixture)


class PublisherFixture(AutoFixture):
    field_values = {
        'name': PublisherGenerator(),
        'num_awards': generators.PositiveIntegerGenerator(min_value=0, max_value=10)
    }
register(Publisher, PublisherFixture)


class BookFixture(AutoFixture):
    generate_fk = True
    generate_m2m = {'authors': (1, 2),
                    'stores': (1, 2)}
    field_values = {
        'name': generators.StringGenerator(min_length=5, max_length=15),
        'pages': generators.PositiveIntegerGenerator(min_value=200, max_value=2000),
        'price': generators.PositiveDecimalGenerator(max_digits=10, decimal_places=2),
        'rating': generators.FloatGenerator(max_value=10, min_value=0, decimal_digits=2),
        'pubdate': generators.DateGenerator(min_date=date.today() - timedelta(days=36500),
                                            max_date=date.today())
    }
register(Book, BookFixture)


class StoreFixture(AutoFixture):
    generate_fk = True
    generate_m2m = {'books': (2, 4)}
    field_values = {
        'name': generators.StringGenerator(min_length=5, max_length=15),
        'registered_users': generators.PositiveSmallIntegerGenerator(10, 1000)
    }
register(Store, StoreFixture)
