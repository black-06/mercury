import unittest
import infra.token


class MyTestCase(unittest.TestCase):

    def test_gen_token(self):
        user_id = 1
        username = "test"

        actual_token = infra.token.gen_token(user_id, username)
        ok = infra.token.check_token(actual_token)
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
