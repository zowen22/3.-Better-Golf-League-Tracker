import SwiftUI

struct LoginView: View {
    @Environment(AuthViewModel.self) private var authVM

    @State private var leagueCode = ""
    @State private var password = ""
    @FocusState private var focusedField: Field?

    private enum Field { case leagueCode, password }

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                Spacer()

                // Logo / Title
                VStack(spacing: 8) {
                    Image(systemName: "figure.golf")
                        .font(.system(size: 52))
                        .foregroundStyle(.green)
                    Text("Golf League Tracker")
                        .font(.title.bold())
                    Text("Enter your league code and password to sign in.")
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                        .multilineTextAlignment(.center)
                }
                .padding(.bottom, 40)

                // Fields
                VStack(spacing: 14) {
                    TextField("League Code", text: $leagueCode)
                        .autocorrectionDisabled()
                        .textInputAutocapitalization(.characters)
                        .keyboardType(.asciiCapable)
                        .focused($focusedField, equals: .leagueCode)
                        .submitLabel(.next)
                        .onSubmit { focusedField = .password }
                        .padding()
                        .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))

                    SecureField("Password", text: $password)
                        .focused($focusedField, equals: .password)
                        .submitLabel(.go)
                        .onSubmit { signIn() }
                        .padding()
                        .background(.quaternary, in: RoundedRectangle(cornerRadius: 10))
                }
                .padding(.horizontal, 28)

                // Error
                if let error = authVM.errorMessage {
                    Text(error)
                        .foregroundStyle(.red)
                        .font(.footnote)
                        .multilineTextAlignment(.center)
                        .padding(.horizontal, 28)
                        .padding(.top, 12)
                }

                // Sign In button
                Button(action: signIn) {
                    Group {
                        if authVM.isLoading {
                            ProgressView()
                                .tint(.white)
                        } else {
                            Text("Sign In")
                                .font(.headline)
                        }
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                }
                .buttonStyle(.borderedProminent)
                .tint(.green)
                .disabled(authVM.isLoading || leagueCode.isEmpty || password.isEmpty)
                .padding(.horizontal, 28)
                .padding(.top, 24)

                Spacer()
                Spacer()
            }
            .navigationBarHidden(true)
            .onTapGesture { focusedField = nil }
        }
    }

    private func signIn() {
        Task { await authVM.login(email: "", password: password, leagueCode: leagueCode) }
    }
}
