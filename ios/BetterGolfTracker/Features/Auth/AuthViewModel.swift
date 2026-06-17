import Foundation
import Observation

@Observable
final class AuthViewModel {
    var isAuthenticated = false
    var currentUser: CurrentUser?
    var isLoading = false
    var errorMessage: String?

    init() {
        if let _ = KeychainStore.loadToken() {
            isAuthenticated = true
            Task { await loadProfile() }
        }
        Task { await setupUnauthorizedHandler() }
    }

    // MARK: - Login

    func login(email: String, password: String, leagueCode: String) async {
        guard !password.isEmpty, !leagueCode.isEmpty else {
            errorMessage = "League code and password are required."
            return
        }
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let response: AuthResponse = try await APIClient.shared.request(
                .login(email: email, password: password, leagueCode: leagueCode)
            )
            KeychainStore.saveToken(response.token)
            currentUser = CurrentUser(
                userId: response.userId,
                leagueId: response.leagueId,
                role: response.role,
                playerId: response.playerId,
                displayName: response.displayName,
                email: nil,
                leagueName: nil
            )
            isAuthenticated = true
            Task { await loadProfile() }
        } catch APIError.unauthorized {
            errorMessage = "Invalid email, password, or league code."
        } catch APIError.noNetwork {
            errorMessage = "No network connection. Please try again."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - Logout

    func logout() {
        KeychainStore.deleteToken()
        currentUser = nil
        isAuthenticated = false
    }

    // MARK: - Profile enrichment

    func loadProfile() async {
        do {
            let me: CurrentUser = try await APIClient.shared.request(.me)
            currentUser?.displayName   = me.displayName
            currentUser?.email         = me.email
            currentUser?.leagueName    = me.leagueName
            currentUser?.handicapIndex = me.handicapIndex
            currentUser?.hcpHistory    = me.hcpHistory
            currentUser?.seasonId      = me.seasonId
            currentUser?.seasonName    = me.seasonName
        } catch {
            // Non-fatal — display name may be missing but session stays valid
        }
    }

    // MARK: - Token refresh

    func refreshTokenIfNeeded() async {
        guard let token = KeychainStore.loadToken() else {
            logout(); return
        }
        do {
            let response: AuthResponse = try await APIClient.shared.request(.refresh(token: token))
            KeychainStore.saveToken(response.token)
        } catch APIError.unauthorized {
            logout()
        } catch {
            // Network error — keep existing token, will retry later
        }
    }

    // MARK: - Unauthorized handler

    private func setupUnauthorizedHandler() async {
        await APIClient.shared.setUnauthorizedHandler { [weak self] in
            self?.logout()
        }
    }
}
